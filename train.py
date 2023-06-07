#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, argparse
import tensorflow.keras.backend as K
#from tensorflow.keras.utils import multi_gpu_model
from tensorflow.keras.callbacks import TensorBoard, TerminateOnNaN

from hourglass.model import get_hourglass_model
from hourglass.data import hourglass_dataset
from hourglass.loss import get_loss
from hourglass.callbacks import EvalCallBack, CheckpointCleanCallBack
from common.utils import get_classes, get_matchpoints, get_model_type, optimize_tf_gpu
from common.model_utils import get_optimizer

# Try to enable Auto Mixed Precision on TF 2.0
os.environ['TF_ENABLE_AUTO_MIXED_PRECISION'] = '1'
os.environ['TF_AUTO_MIXED_PRECISION_GRAPH_REWRITE_IGNORE_PERFORMANCE'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf
optimize_tf_gpu(tf, K)


def main(args):
    log_dir = 'logs/000'
    os.makedirs(log_dir, exist_ok=True)

    class_names = get_classes(args.classes_path)
    num_classes = len(class_names)
    if args.matchpoint_path:
        matchpoints = get_matchpoints(args.matchpoint_path)
    else:
        matchpoints = None

    # choose model type
    if args.tiny:
        num_channels = 128
    else:
        num_channels = 256

    if args.mixed_precision:
        tf_major_version = float(tf.__version__[:3])
        if tf_major_version >= 2.1:
            # apply mixed_precision for valid TF version
            from tensorflow.keras.mixed_precision import experimental as mixed_precision

            policy = mixed_precision.Policy('mixed_float16')
            mixed_precision.set_policy(policy)
        else:
            raise ValueError('Tensorflow {} does not support mixed precision'.format(tf.__version__))


    # get train/val dataset
    train_generator = hourglass_dataset(args.dataset_path, args.batch_size, class_names,
                                        input_shape=args.model_input_shape,
                                        num_hgstack=args.num_stacks,
                                        is_train=True,
                                        with_meta=False,
                                        matchpoints=matchpoints)

    num_train = train_generator.get_dataset_size()
    num_val = len(train_generator.get_val_annotations())

    model_type = get_model_type(args.num_stacks, args.mobile, args.tiny, args.model_input_shape)

    # callbacks for training process
    tensorboard = TensorBoard(log_dir=log_dir, histogram_freq=0, write_graph=False, write_grads=False, write_images=False, update_freq='batch')
    eval_callback = EvalCallBack(log_dir, args.dataset_path, class_names, args.model_input_shape, model_type)
    checkpoint_clean = CheckpointCleanCallBack(log_dir, max_val_keep=5)
    terminate_on_nan = TerminateOnNaN()

    callbacks = [tensorboard, eval_callback, terminate_on_nan, checkpoint_clean]

    # prepare optimizer
    steps_per_epoch = max(1, num_train//args.batch_size)
    decay_steps = steps_per_epoch * (args.total_epoch - args.init_epoch)
    optimizer = get_optimizer(args.optimizer, args.learning_rate, decay_type=args.decay_type, decay_steps=decay_steps)
    #optimizer = RMSprop(lr=5e-4)

    # prepare loss function
    loss_func = get_loss(args.loss_type)

    # support multi-gpu training
    if args.gpu_num >= 2:
        # devices_list=["/gpu:0", "/gpu:1"]
        devices_list=["/gpu:{}".format(n) for n in range(args.gpu_num)]
        strategy = tf.distribute.MirroredStrategy(devices=devices_list)
        print ('Number of devices: {}'.format(strategy.num_replicas_in_sync))
        with strategy.scope():
            # get multi-gpu train model. you can also use "model_input_shape=None" to create a dynamic input shape model,
            # but multiscale train/inference doesn't work for it
            model = get_hourglass_model(num_classes, args.num_stacks, num_channels, model_input_shape=args.model_input_shape, mobile=args.mobile)
            # compile model
            model.compile(optimizer=optimizer, loss=loss_func)
    else:
        # get normal train model. you can also use "model_input_shape=None" to create a dynamic input shape model,
        # but multiscale train/inference doesn't work for it
        model = get_hourglass_model(num_classes, args.num_stacks, num_channels, model_input_shape=args.model_input_shape, mobile=args.mobile)
        # compile model
        model.compile(optimizer=optimizer, loss=loss_func)

    print('Create {} Stacked Hourglass model with stack number {}, channel number {}. train input shape {}'.format('Mobile' if args.mobile else '', args.num_stacks, num_channels, args.model_input_shape))
    model.summary()

    if args.weights_path:
        model.load_weights(args.weights_path, by_name=True)#, skip_mismatch=True)
        print('Load weights {}.'.format(args.weights_path))

    # start training
    print('Train on {} samples, val on {} samples, with batch size {}, model input shape {}.'.format(num_train, num_val, args.batch_size, args.model_input_shape))
    model.fit_generator(generator=train_generator,
                        steps_per_epoch=num_train // args.batch_size,
                        epochs=args.total_epoch,
                        initial_epoch=args.init_epoch,
                        workers=1,
                        use_multiprocessing=False,
                        max_queue_size=10,
                        callbacks=callbacks)

    model.save(os.path.join(log_dir, 'trained_final.h5'))
    return



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Model definition options
    parser.add_argument("--num_stacks", type=int, required=False, default=2,
        help='number of hourglass stacks, default=%(default)s')
    parser.add_argument("--mobile", default=False, action="store_true",
        help="use depthwise conv in hourglass'")
    parser.add_argument("--tiny", default=False, action="store_true",
        help="tiny network for speed, feature channel=128")
    parser.add_argument('--model_input_shape', type=str, required=False, default='256x256',
        help = "model image input shape as <height>x<width>, default=%(default)s")
    parser.add_argument('--weights_path', type=str, required=False, default=None,
        help = "Pretrained model/weights file for fine tune")

    # Data options
    parser.add_argument('--dataset_path', type=str, required=False, default='data/mpii',
        help='dataset path containing images and annotation file, default=%(default)s')
    parser.add_argument('--classes_path', type=str, required=False, default='configs/mpii_classes.txt',
        help='path to keypoint class definitions, default=%(default)s')
    parser.add_argument('--matchpoint_path', type=str, required=False, default='configs/mpii_match_point.txt',
        help='path to matching keypoint definitions for horizontal/vertical flipping image, default=%(default)s')

    # Training options
    parser.add_argument("--batch_size", type=int, required=False, default=16,
        help='batch size for training, default=%(default)s')
    parser.add_argument('--optimizer', type=str, required=False, default='rmsprop',
        help = "optimizer for training (adam/rmsprop/sgd), default=%(default)s")
    parser.add_argument('--loss_type', type=str, required=False, default='mse', choices=['mse', 'mae', 'weighted_mse', 'smooth_l1', 'huber'],
        help = "loss type for training (mse/mae/weighted_mse/smooth_l1/huber), default=%(default)s")
    parser.add_argument('--learning_rate', type=float, required=False, default=5e-4,
        help = "Initial learning rate, default=%(default)s")
    parser.add_argument('--decay_type', type=str, required=False, default=None, choices=[None, 'cosine', 'exponential', 'polynomial', 'piecewise_constant'],
        help = "Learning rate decay type, default=%(default)s")
    parser.add_argument('--mixed_precision', default=False, action="store_true",
        help='Use mixed precision mode in training, only for TF>2.1')
    parser.add_argument("--init_epoch", type=int, required=False, default=0,
        help="initial training epochs for fine tune training, default=%(default)s")
    parser.add_argument("--total_epoch", type=int, required=False, default=100,
        help="total training epochs, default=%(default)s")
    parser.add_argument('--gpu_num', type=int, required=False, default=1,
        help='Number of GPU to use, default=%(default)s')

    args = parser.parse_args()
    height, width = args.model_input_shape.split('x')
    args.model_input_shape = (int(height), int(width))

    main(args)
