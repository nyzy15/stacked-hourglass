cmake_minimum_required(VERSION 3.5)
project(hourglassKeypoint LANGUAGES CXX)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
SET(CMAKE_BUILD_TYPE "Debug")
#SET(CMAKE_BUILD_TYPE "Release")

#### specify the compiler flag
SET(CMAKE_CXX_FLAGS  "-std=c++14 -O2")

set(HOURGLASS_KEYPOINT_SRC
        hourglassKeypoint.cpp)

#set(MNN_ROOT_PATH /mnt/d/Projects/MNN)
link_directories("${MNN_ROOT_PATH}/build/")

add_executable(hourglassKeypoint ${HOURGLASS_KEYPOINT_SRC})

target_include_directories(hourglassKeypoint PRIVATE ${MNN_ROOT_PATH}/include/ ${MNN_ROOT_PATH}/3rd_party/imageHelper/)
target_link_libraries(hourglassKeypoint PRIVATE -lMNN -lstdc++ -lpthread)
#target_link_libraries(hourglassKeypoint PRIVATE libMNN.a -Wl,--whole-archive -Wl,--no-whole-archive -lstdc++ -lpthread)
