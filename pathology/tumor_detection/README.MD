# Example pipelines for detecting tumors on histopathology whole slide images

## Description

Here we use a classification model to classify small batches extracted from very large whole-slide histopathology images. Since the patches are very small compared to the whole image, we can then use this model for the detection of tumors in a different area of a whole-slide pathology image.

## Model Overview

The model is based on ResNet18 with the last fully connected layer replaced by a 1x1 convolution layer.

## Pre-trained weights
A pre-trained encoder weights would be beneficial for the model training. In this tutorial, you can use `--pretrain` to activate the pre-trained weights on the [ImageNet dataset](https://ieeexplore.ieee.org/document/5206848).

Each user is responsible for checking the content of models/datasets and the applicable licenses and determining if suitable for the intended use.
The license for the pre-trained model used in examples is different than MONAI license. Please check the source where these weights are obtained from.

## Data

All the data used to train and validate this model is from the [Camelyon-16 Challenge](https://camelyon16.grand-challenge.org/). You can download all the images for the "CAMELYON16" data set from various sources listed [here](https://camelyon17.grand-challenge.org/Data/).

Location information for training/validation patches (the location on the whole slide image where patches are extracted) is adopted from [NCRF/coords](https://github.com/baidu-research/NCRF/tree/master/coords). The reformatted coordinations and labels in CSV format for training (`training.csv`) can be found [here](https://developer.download.nvidia.com/assets/Clara/monai/tutorials/pathology_train.csv) and for validation (`validation.csv`) can be found [here](https://developer.download.nvidia.com/assets/Clara/monai/tutorials/pathology_validation.csv).

This pipeline expects the training/validation data (whole slide images) reside in `cfg["data_root"]/training/images`. By default `data_root` is pointing to the code folder `./`; however, you can easily modify it to point to a different directory by passing the following argument in the runtime: `--data-root /other/data/root/dir/`.

> [`training_sub.csv`](https://developer.download.nvidia.com/assets/Clara/monai/tutorials/pathology_train_sub.csv) and [`validation_sub.csv`](https://developer.download.nvidia.com/assets/Clara/monai/tutorials/pathology_validation_sub.csv) is also provided to check the functionality of the pipeline using only two of the whole slide images: `tumor_001` (for training) and `tumor_101` (for validation). This dataset should not be used for the real training or any performance evaluation.

### Input and output formats

Input for the training pipeline is a JSON file (dataset.json) which includes the path to each WSI, the location and the label information for each training patch.

The output of the network is the probability of whether the input patch contains the tumor or not.

## Disclaimer

This is an example, not to be used for diagnostic purposes.
