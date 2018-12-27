# 2D U-Net for Medical Decathlon Dataset

![prediction4385](https://github.com/IntelAI/unet/blob/master/single-node/images/pred4385.png)


Trains a 2D U-Net on the brain tumor segmentation (BraTS) subset of the [Medical Segmentation Decathlon](http://medicaldecathlon.com/) dataset.

Steps:
1. Go to the [Medical Segmentation Decathlon](http://medicaldecathlon.com) website and download the [BraTS subset](https://drive.google.com/file/d/1A2IU8Sgea1h3fYLpYtFb2v7NYdMjvEhU/view?usp=sharing). The dataset has the Creative Commons Attribution-ShareAlike 4.0 International [license](https://creativecommons.org/licenses/by-sa/4.0/).
2. Untar the "Task01_BrainTumour.tar" file (e.g. `tar -xvf Task01_BrainTumour.tar`)
3. Create a Conda environment with TensorFlow 1.12. Command: `conda create -c anaconda -n decathlon pip python=3.6 tensorflow keras`
4. Enable the new environment. Command: `conda activate decathlon`
5. Install the packages `nibabel`, `h5py`, `tqdm`, and `psutil`. Command: `pip install nibabel h5py tqdm psutil`
6. Run the command `bash run_brats_model.sh DECATHLON_ROOT_DIRECTORY`, where DECATHLON_ROOT_DIRECTORY is the root directory where you un-tarred the Decathlon dataset.
7. The bash script should pre-process the Decathlon data and store it in a new HDF5 file (`convert_raw_to_hdf5.py`). Then it trains a U-Net model (`train.py`). Finally, it performs inference on a handful of MRI slices in the validation dataset (`plot_inference_examples.py`).  You should be able to get a model to train to a Dice of over 0.85 on the validation set within 20 epochs.

Tips for improving model:
* The feature maps have been reduced so that the model will train using under 12GB of memory.  If you have more memory to use, consider increasing the `fms = 16` on line 236 in `train.py` to something larger (e.g. `fms = 32` or even `fms = 64`. This will increase the complexity of the model (which will also increase its memory footprint but decrease its execution speed).
* Consider different loss functions.  The default loss function here is a weighted sum of `-log(Dice)` and `binary_crossentropy`. Different loss functions yield different loss curves and may result in better accuracy. However, you may need to adjust the `learning_rate` and number of epochs to train as you experiment with different loss functions.
* Predict multiple output masks.  In `convert_raw_to_hdf5.py` we have combined all of the ground truth masks into one single mask. However, more complex models predict each of the subclasses (edema, tumor core, necrosis) of the glioma. This will involve some modification of the output layer to the model (e.g. more output layers for the sigmoid mask or a softmax layer at the output instead of a sigmoid).

![prediction61](https://github.com/IntelAI/unet/blob/master/single-node/images/pred61.png)