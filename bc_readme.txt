
~ https://github.com/david8862/tf-keras-stacked-hourglass-keypoint-detection

conda create -n test python=3.8

pip install -r requirements_new.txt

python multi_person_demo_stu.py --num_stacks=2 --weights_path=./models/hg_s2_256_256_coco.h5 \
 --classes_path=configs/coco_classes.txt --skeleton_path=configs/coco_skeleton.txt \
 --input_folder=example --output=out



#apt install python3-opencv
