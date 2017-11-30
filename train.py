# '''
# BEGIN - Limit Tensoflow to only use specific GPU
# '''
# import os

# gpu_num = 0

# os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'   # see issue #152
# os.environ['CUDA_VISIBLE_DEVICES'] = '{}'.format(gpu_num)
# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' # Supress Tensforflow debug messages

# # '''
# # END - Limit Tensoflow to only use specific GPU
# # '''

# numactl -p 1 python train.py --num_threads=50 --num_inter_threads=5 --batch_size=256 --blocktime=0
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--use_upsampling', help='use upsampling instead of transposed convolution',
					action='store_true', default=False)
parser.add_argument("--num_threads", type=int, default=50, help="the number of threads")
parser.add_argument("--num_inter_threads", type=int, default=2, help="the number of intraop threads")
parser.add_argument("--batch_size", type=int, default=128, help="the batch size for training")
parser.add_argument("--blocktime", type=int, default=0, help="blocktime")
parser.add_argument("--epochs", type=int, default=10, help="number of epochs to train")
parser.add_argument("--learningrate", type=float, default=0.0001, help="learningrate")


args = parser.parse_args()

batch_size = args.batch_size

import os

num_threads = args.num_threads
num_inter_op_threads = args.num_inter_threads

if (args.blocktime > 1000):
	blocktime = 'infinite'
else:
	blocktime = str(args.blocktime)

EPOCHS = args.epochs
learningrate = args.learningrate


os.environ['TF_CPP_MIN_LOG_LEVEL']='2'  # Get rid of the AVX, SSE warnings

os.environ["KMP_BLOCKTIME"] = blocktime
os.environ["KMP_AFFINITY"]="compact,1,0,granularity=thread"
#os.environ["KMP_AFFINITY"]="compact,1,0,granularity=fine"
#os.environ['KMP_AFFINITY']='granularity=fine,proclist=[0-{}],explicit'.format(num_threads)

os.environ["OMP_NUM_THREADS"]= str(num_threads)
os.environ["TF_ADJUST_HUE_FUSED"] = '1'
os.environ['TF_ADJUST_SATURATION_FUSED'] = '1'
#os.environ['MKL_VERBOSE'] = '1'
os.environ['MKL_DYNAMIC']='1'
os.environ['INTRA_THREADS']=str(num_threads)
os.environ['INTER_THREADS']=str(num_inter_op_threads)
# os.environ['MIC_ENV_PREFIX'] = 'PHI'
# os.environ['PHI_KMP_AFFINITY'] = 'compact'
# os.environ['PHI_KMP_PLACE_THREADS'] = '60c,3t'
# os.environ['PHI_OMP_NUM_THREADS'] = str(num_threads)

os.environ['TF_ENABLE_WINOGRAD_NONFUSED'] = '1'
os.environ['TF_AUTOTUNE_THRESHOLD'] = '1'

os.environ['MKL_NUM_THREADS'] =str(num_threads)

os.environ['KMP_SETTINGS'] = '0'  # Show the settins at runtime

# The timeline trace for TF is saved to this file.
# To view it, run this python script, then load the json file by 
# starting Google Chrome browser and pointing the URI to chrome://trace
# There should be a button at the top left of the graph where
# you can load in this json file.
timeline_filename = 'timeline_ge_unet_{}_{}_{}.json'.format(blocktime, num_threads, num_inter_op_threads)

import time

import tensorflow as tf



# configuration session
# sess = tf.Session(config=tf.ConfigProto(
# 	   intra_op_parallelism_threads=num_threads, inter_op_parallelism_threads=num_inter_op_threads))

# config = tf.ConfigProto(device_count={"CPU": 16},
#                         intra_op_parallelism_threads=num_threads, inter_op_parallelism_threads=num_inter_op_threads)

config = tf.ConfigProto(intra_op_parallelism_threads=num_threads, inter_op_parallelism_threads=num_inter_op_threads)

config.graph_options.optimizer_options.opt_level = -1

sess = tf.Session(config=config)

run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
run_metadata = tf.RunMetadata()  # For Tensorflow trace

from keras import backend as K
#K.set_session(sess)

CHANNEL_LAST = True
if CHANNEL_LAST:
	concat_axis = -1
	data_format = 'channels_last'
	K.set_image_dim_ordering('tf')	
else:
	concat_axis = 1
	data_format = 'channels_first'
	K.set_image_dim_ordering('th')	


from keras.callbacks import ModelCheckpoint, TensorBoard, LearningRateScheduler
from keras.callbacks import History 
from keras.models import Model

import numpy as np
import os

from preprocess import * 
from helper import *
import settings

from keras.preprocessing.image import ImageDataGenerator

def model5_MultiLayer(args=None, weights=False, 
	filepath="", 
	img_rows = 224, 
	img_cols = 224, 
	n_cl_in=3,
	n_cl_out=3, 
	dropout=0.2, 
	learning_rate = 0.01,
	print_summary = False):
	""" difference from model: img_rows and cols, order of axis, and concat_axis"""
	
	if args.use_upsampling:
		print ('Using UpSampling2D')
	else:
		print('Using Transposed Deconvolution')

	if CHANNEL_LAST:
		inputs = Input((img_rows, img_cols, n_cl_in), name='Images')
	else:
		inputs = Input((n_cl_in, img_rows, img_cols), name='Images')



	params = dict(kernel_size=(3, 3), activation='relu', 
				  padding='same', data_format=data_format,
				  kernel_initializer='he_uniform') #RandomUniform(minval=-0.01, maxval=0.01, seed=816))

	conv1 = Conv2D(name='conv1a', filters=32, **params)(inputs)
	conv1 = Conv2D(name='conv1b', filters=32, **params)(conv1)
	pool1 = MaxPooling2D(name='pool1', pool_size=(2, 2))(conv1)

	conv2 = Conv2D(name='conv2a', filters=64, **params)(pool1)
	conv2 = Conv2D(name='conv2b', filters=64, **params)(conv2)
	pool2 = MaxPooling2D(name='pool2', pool_size=(2, 2))(conv2)

	conv3 = Conv2D(name='conv3a', filters=128, **params)(pool2)
	conv3 = Dropout(dropout)(conv3) ### Trying dropout layers earlier on, as indicated in the paper
	conv3 = Conv2D(name='conv3b', filters=128, **params)(conv3)
	
	pool3 = MaxPooling2D(name='pool3', pool_size=(2, 2))(conv3)

	conv4 = Conv2D(name='conv4a', filters=256, **params)(pool3)
	conv4 = Dropout(dropout)(conv4) ### Trying dropout layers earlier on, as indicated in the paper
	conv4 = Conv2D(name='conv4b', filters=256, **params)(conv4)
	
	pool4 = MaxPooling2D(name='pool4', pool_size=(2, 2))(conv4)

	conv5 = Conv2D(name='conv5a', filters=512, **params)(pool4)
	

	if args.use_upsampling:
		conv5 = Conv2D(name='conv5b', filters=256, **params)(conv5)
		up6 = concatenate([UpSampling2D(name='up6', size=(2, 2))(conv5), conv4], axis=concat_axis)
	else:
		conv5 = Conv2D(name='conv5b', filters=512, **params)(conv5)
		up6 = concatenate([Conv2DTranspose(name='transConv6', filters=256, data_format=data_format,
			               kernel_size=(2, 2), strides=(2, 2), padding='same')(conv5), conv4], axis=concat_axis)
		
	conv6 = Conv2D(name='conv6a', filters=256, **params)(up6)
	

	if args.use_upsampling:
		conv6 = Conv2D(name='conv6b', filters=128, **params)(conv6)
		up7 = concatenate([UpSampling2D(name='up7', size=(2, 2))(conv6), conv3], axis=concat_axis)
	else:
		conv6 = Conv2D(name='conv6b', filters=256, **params)(conv6)
		up7 = concatenate([Conv2DTranspose(name='transConv7', filters=128, data_format=data_format,
			               kernel_size=(2, 2), strides=(2, 2), padding='same')(conv6), conv3], axis=concat_axis)

	conv7 = Conv2D(name='conv7a', filters=128, **params)(up7)
	

	if args.use_upsampling:
		conv7 = Conv2D(name='conv7b', filters=64, **params)(conv7)
		up8 = concatenate([UpSampling2D(name='up8', size=(2, 2))(conv7), conv2], axis=concat_axis)
	else:
		conv7 = Conv2D(name='conv7b', filters=128, **params)(conv7)
		up8 = concatenate([Conv2DTranspose(name='transConv8', filters=64, data_format=data_format,
			               kernel_size=(2, 2), strides=(2, 2), padding='same')(conv7), conv2], axis=concat_axis)

	
	conv8 = Conv2D(name='conv8a', filters=64, **params)(up8)
	
	if args.use_upsampling:
		conv8 = Conv2D(name='conv8b', filters=32, **params)(conv8)
		up9 = concatenate([UpSampling2D(name='up9', size=(2, 2))(conv8), conv1], axis=concat_axis)
	else:
		conv8 = Conv2D(name='conv8b', filters=64, **params)(conv8)
		up9 = concatenate([Conv2DTranspose(name='transConv9', filters=32, data_format=data_format,
			               kernel_size=(2, 2), strides=(2, 2), padding='same')(conv8), conv1], axis=concat_axis)


	conv9 = Conv2D(name='conv9a', filters=32, **params)(up9)
	conv9 = Conv2D(name='conv9b', filters=32, **params)(conv9)

	conv10 = Conv2D(name='Mask', filters=n_cl_out, kernel_size=(1, 1), 
					data_format=data_format, activation='sigmoid')(conv9)

	model = Model(inputs=[inputs], outputs=[conv10])

	# if weights:
	# 	optimizer=Adam(lr=0.0001, beta_1=0.9, beta_2=0.99, epsilon=1e-08, decay=0.01)
	# else:
	# 	optimizer = SGD(lr=learning_rate, momentum=0.9, decay=0.05)

	optimizer=Adam(lr=args.learningrate, beta_1=0.9, beta_2=0.99, epsilon=1e-08, decay=0.00001)

	model.compile(optimizer=optimizer,
		loss=dice_coef_loss, #dice_coef_loss, #'binary_crossentropy', 
		metrics=['accuracy', dice_coef], options=run_options, run_metadata=run_metadata)

	if weights and os.path.isfile(filepath):
		print('Loading model weights from file {}'.format(filepath))
		model.load_weights(filepath)

	if print_summary:
		print (model.summary())	

	return model

def image_augmentation(imgs, masks): 
	'''
	This will perform image augmentation on BOTH the
	image and mask. It returns a generator so that
	every time it is called it will grab a new batch
	and perform a random augmentation.
	'''
	data_gen_args = dict(shear_range=0.5,  #radians
						 rotation_range=90., # degrees
						 width_shift_range=0.1,
						 height_shift_range=0.1,
						 zoom_range=0.2, # +/- 20%
						 horizontal_flip=True,
						 vertical_flip = True)

	image_datagen = ImageDataGenerator(**data_gen_args)
	mask_datagen = ImageDataGenerator(**data_gen_args)

	# Provide the same seed and keyword arguments to the fit and flow methods
	# This should ensure that the same augmentations are done for the image and the mask.
	seed = 816
	image_datagen.fit(imgs, augment=True, seed=seed)
	mask_datagen.fit(masks, augment=True, seed=seed)

	# Create a batch generator for the images
	image_generator = image_datagen.flow(
		imgs,
		batch_size=batch_size,
		shuffle=True,
		seed=seed)

	# Create a batch generator for the masks
	mask_generator = mask_datagen.flow(
		masks,
		batch_size=batch_size,
		shuffle=True,
		seed=seed)

	# The generator needs to be an infinite loop that 
	# yields after each batch (next). Otherwise, it will
	# try to perform augmentation on the entire dataset and (probably) crash.
	while True:
		yield (image_generator.next(), mask_generator.next())


def train_and_predict(data_path, img_rows, img_cols, n_epoch, input_no  = 3, output_no = 3,
	fn= "model", mode = 1, args=None):
	
	print('-'*30)
	print('Loading and preprocessing train data...')
	print('-'*30)
	imgs_train, msks_train = load_data(data_path,"_train")
	imgs_train, msks_train = update_channels(imgs_train, msks_train, input_no, output_no, 
		mode)

	if not CHANNEL_LAST:
		imgs_train = np.transpose(imgs_train, [0,3,1,2])
		msks_train = np.transpose(msks_train, [0,3,1,2])
	
	print('-'*30)
	print('Loading and preprocessing test data...')
	print('-'*30)
	imgs_test, msks_test = load_data(data_path,"_test")
	imgs_test, msks_test = update_channels(imgs_test, msks_test, input_no, output_no, mode)

	if not CHANNEL_LAST:
		imgs_test = np.transpose(imgs_test, [0,3,1,2])
		msks_test = np.transpose(msks_test, [0,3,1,2])

	print('-'*30)
	print('Creating and compiling model...')
	print('-'*30)

	model = model5_MultiLayer(args, False, False, img_rows, img_cols, input_no, output_no)

	if (args.use_upsampling):
		model_fn	= os.path.join(data_path, fn+'_upsampling.hdf5')
	else:
		model_fn	= os.path.join(data_path, fn+'_transposed.hdf5')

	print ("Writing model to ", model_fn)

	model_checkpoint = ModelCheckpoint(model_fn, monitor='loss', save_best_only=True) 

	directoryName = 'unet_block{}_inter{}_intra{}'.format(blocktime, num_threads, num_inter_op_threads)

	if (args.use_upsampling):
		tensorboard_checkpoint = TensorBoard(
			log_dir='./keras_tensorboard_upsampling_batch{}/{}'.format(batch_size, directoryName), 
			write_graph=True, write_images=True)
	else:
		tensorboard_checkpoint = TensorBoard(
			log_dir='./keras_tensorboard_transposed_batch{}/{}'.format(batch_size, directoryName),
			write_graph=True, write_images=True)
	

	print('-'*30)
	print('Fitting model...')
	print('-'*30)
	history = History()

	print('Batch size = {}'.format(batch_size))

	# # '''
	# # For image augmentation use model.fit_generator instead of model.fit
	# # '''
	# train_generator = image_augmentation(imgs_train, msks_train)

	# # fits the model on batches with real-time data augmentation:
	# history = model.fit_generator(train_generator,
	# 				steps_per_epoch=len(imgs_train) // batch_size, epochs=n_epoch, validation_data = (imgs_test, msks_test),
	# 				callbacks=[model_checkpoint, tensorboard_checkpoint])

	'''
	 Without image augmentation just use model.fit
	'''
	history = model.fit(imgs_train, msks_train, 
	 	batch_size=batch_size, 
	 	epochs=n_epoch, 
	 	validation_data = (imgs_test, msks_test),
	 	verbose=1, 
	 	callbacks=[model_checkpoint, tensorboard_checkpoint])

	# model = model5_MultiLayer(args, True, model_fn, img_rows, img_cols, input_no, output_no)

	# history = model.fit(imgs_train, msks_train, 
	#  	batch_size=batch_size, 
	#  	epochs=n_epoch-2, 
	#  	validation_data = (imgs_test, msks_test),
	#  	verbose=1, 
	#  	callbacks=[model_checkpoint, tensorboard_checkpoint])

	json_fn = os.path.join(data_path, fn+'.json')
	with open(json_fn,'w') as f:
		f.write(model.to_json())


	'''
	Save the training timeline
	'''
	from tensorflow.python.client import timeline

	fetched_timeline = timeline.Timeline(run_metadata.step_stats)
	chrome_trace = fetched_timeline.generate_chrome_trace_format()
	with open(timeline_filename, 'w') as f:
		print('Saved Tensorflow trace to: {}'.format(timeline_filename))
		f.write(chrome_trace)

	print('-'*30)
	print('Loading saved weights...')
	print('-'*30)
	epochNo = len(history.history['loss'])-1
	#model_fn	= os.path.join(data_path, '{}_{:03d}.hdf5'.format(fn, epochNo))
	model.load_weights(model_fn)

	print('-'*30)
	print('Predicting masks on test data...')
	print('-'*30)
	msks_pred = model.predict(imgs_test, verbose=1)
	
	#np.save(os.path.join(data_path, 'msks_pred.npy'), msks_pred)

	print('Saving predictions to file')
	if (args.use_upsampling):
		np.save('msks_pred_upsampling.npy', msks_pred)
	else:
		np.save('msks_pred_transposed.npy', msks_pred)

	print('Evaluating model')
	scores = model.evaluate(imgs_test, msks_test, batch_size=batch_size, verbose = 2)
	print ("Evaluation Scores", scores)

if __name__ =="__main__":

	import datetime
	print(datetime.datetime.now())
	
	start_time = time.time()

	train_and_predict(settings.OUT_PATH, settings.IMG_ROWS/settings.RESCALE_FACTOR, 
		settings.IMG_COLS/settings.RESCALE_FACTOR, 
		EPOCHS, settings.IN_CHANNEL_NO, \
		settings.OUT_CHANNEL_NO, settings.MODEL_FN, settings.MODE, args)

	print('Total time elapsed for program = {} seconds'.format(time.time() - start_time))
	print(datetime.datetime.now())


