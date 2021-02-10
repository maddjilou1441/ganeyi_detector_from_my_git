"""
Retrain the YOLO model for your own dataset.
"""

import numpy as np
import keras.backend as K
from keras.layers import Input, Lambda
from keras.models import Model
from keras.optimizers import Adam
from keras.callbacks import TensorBoard, ModelCheckpoint, ReduceLROnPlateau, EarlyStopping

from yolo3.model import preprocess_true_boxes, yolo_body, tiny_yolo_body, yolo_loss
from yolo3.utils import get_random_data

from keras.utils import plot_model  # plot model
import argparse

def _main(annotation_path, classes_path, output_model_path):
    # return
    annotation_path = annotation_path
    log_dir = 'logs/000/'
    classes_path = classes_path
    anchors_path = '/home/madiou/Documents/A-Baamtu/learning_step/ob_detect/Eau/data_w_aug/yolo_anchors_passort.txt'
    class_names = get_classes(classes_path)
    num_classes = len(class_names)
    anchors = get_anchors(anchors_path)


    input_shape = (416,416) # multiple of 32, hw

    is_tiny_version = len(anchors)==6 # default setting
    if is_tiny_version:
        model = create_tiny_model(input_shape, anchors, num_classes,
            freeze_body=2, weights_path='model_data/tiny_yolo_weights.h5')
    else:
        model = create_model(input_shape, anchors, num_classes,
            freeze_body=2, weights_path='/home/madiou/Documents/A-Baamtu/learning_step/ob_detect/Eau/data_w_aug/output_model_weights_passport.h5') # make sure you know what you freeze
    # model.save('yolo_model_retrain.h5')  # creates a HDF5 file 'my_model.h5'

    print(model.input)
    print(model.output)
    #plot_model(model, to_file='model_data/retrained_model.png', show_shapes = True)

    logging = TensorBoard(log_dir=log_dir)
    checkpoint = ModelCheckpoint('/home/madiou/Documents/A-Baamtu/learning_step/ob_detect/Eau/output/' + 'detector_checkpoint.h5',
          monitor='val_loss', save_weights_only=True, save_best_only=True, period=4)
    reduce_lr = ReduceLROnPlateau(monitor='val_loss', factor=0.1, patience=3, verbose=1)
    early_stopping = EarlyStopping(monitor='val_loss', min_delta=0, patience=10, verbose=1)

    val_split = 0.1
    with open(annotation_path) as f:
        lines = f.readlines()
    np.random.seed(10101)
    np.random.shuffle(lines)
    np.random.seed(None)
    num_val = int(len(lines)*val_split)
    num_train = len(lines) - num_val

    # Train with frozen layers first, to get a stable loss.
    # Adjust num epochs to your dataset. This step is enough to obtain a not bad model.
    if True:
        # model.compile(optimizer=Adam(lr=1e-3), loss={
        #     # use custom yolo_loss Lambda layer.
        #     'yolo_loss': lambda y_true, y_pred: y_pred})

        model.compile(optimizer=Adam(lr=1e-3), loss='mean_squared_error')

        batch_size = 16
        print('Train on {} samples, val on {} samples, with batch size {}.'.format(num_train, num_val, batch_size))
        model.fit_generator(data_generator_wrapper(lines[:num_train], batch_size, input_shape, anchors, num_classes),
                steps_per_epoch=max(1, num_train//batch_size),
                validation_data=data_generator_wrapper(lines[num_train:], batch_size, input_shape, anchors, num_classes),
                validation_steps=max(1, num_val//batch_size),
                epochs=28,
                initial_epoch=0,
                callbacks=[logging, checkpoint])
        model.save_weights('/home/madiou/Documents/A-Baamtu/learning_step/ob_detect/Eau/output/' + 'trained_weights_stage_1.h5')
#         model.save('/home/madiou/Documents/A-Baamtu/learning_step/ganeyi_detector' + 'trained_model_stage_1.h5')

    # Unfreeze and continue training, to fine-tune.
    # Train longer if the result is not good.
    if True:
        for i in range(len(model.layers)):
            model.layers[i].trainable = True
        model.compile(optimizer=Adam(lr=1e-4), loss='mean_squared_error') # recompile to apply the change
        print('Unfreeze all of the layers.')

        batch_size = 1 # note that more GPU memory is required after unfreezing the body
        print('Train on {} samples, val on {} samples, with batch size {}.'.format(num_train, num_val, batch_size))
        model.fit_generator(data_generator_wrapper(lines[:num_train], batch_size, input_shape, anchors, num_classes),
            steps_per_epoch=max(1, num_train//batch_size),
            validation_data=data_generator_wrapper(lines[num_train:], batch_size, input_shape, anchors, num_classes),
            validation_steps=max(1, num_val//batch_size),
            epochs=40,
            initial_epoch=28,
            callbacks=[logging, checkpoint, reduce_lr, early_stopping])
        model.save_weights('/home/madiou/Documents/A-Baamtu/learning_step/ob_detect/Eau/output/' + 'trained_weights_final.h5')
        # model.save(log_dir + 'trained_model_final.h5')

    # Further training if needed.
    

    # print('model.input = ',model.input)
    # print('len(model.layers) = ',len(model.layers))
    # print('model.layers[-1]: ',model.layers[-1].output)
    # print('model.layers[-2]: ',model.layers[-2].output)
    # print('model.layers[-3]: ',model.layers[-3].output)
    # print('model.layers[-4]: ',model.layers[-4].output,'\n')
    # # original yolo model outputs:
    # print('model.layers[-5]: ',model.layers[-5].output)
    # print('model.layers[-6]: ',model.layers[-6].output)
    # print('model.layers[-7]: ',model.layers[-7].output)

    # save the derived model for detection(using yolo_video.py)
    derived_model = Model(model.input[0], [model.layers[249].output, model.layers[250].output, model.layers[251].output])
    plot_model(derived_model, to_file=output_model_path[:-3]+'.png', show_shapes = True)
    print('*************')
    derived_model.save(output_model_path)
    print('&&&&&&&&&&&&&')


def get_classes(classes_path):
    '''loads the classes'''
    with open(classes_path) as f:
        class_names = f.readlines()
    class_names = [c.strip() for c in class_names]
    return class_names

def get_anchors(anchors_path):
    '''loads the anchors from a file'''
    with open(anchors_path) as f:
        anchors = f.readline()
    anchors = [float(x) for x in anchors.split(',')]
    return np.array(anchors).reshape(-1, 2)


def create_model(input_shape, anchors, num_classes, load_pretrained=True, freeze_body=2,
            weights_path='/home/madiou/Documents/A-Baamtu/learning_step/ob_detect/Eau/data_w_aug/best_output_model_weights_passport.h5'):
    '''create the training model'''
    K.clear_session() # get a new session
    image_input = Input(shape=(None, None, 3))
    h, w = input_shape
    num_anchors = len(anchors)

    # y_true = [Input(shape=(416//{0:32, 1:16, 2:8}[l], 416//{0:32, 1:16, 2:8}[l], 9//3, 80+5)) for l in range(3)]
    y_true = [Input(shape=(h//{0:32, 1:16, 2:8}[l], w//{0:32, 1:16, 2:8}[l], num_anchors//3, num_classes+5)) for l in range(3)]

    model_body = yolo_body(image_input, num_anchors//3, num_classes)
    print('Create YOLOv3 model with {} anchors and {} classes.'.format(num_anchors, num_classes))

    if load_pretrained:
        model_body.load_weights(weights_path, by_name=True, skip_mismatch=True)
        print('Load weights {}.'.format(weights_path))
        if freeze_body in [1, 2]:
            # Freeze darknet53 body or freeze all but 3 output layers.
            num = (185, len(model_body.layers)-3)[freeze_body-1]
            for i in range(num): model_body.layers[i].trainable = False
            print('Freeze the first {} layers of total {} layers.'.format(num, len(model_body.layers)))

    model_loss = Lambda(yolo_loss, output_shape=(1,), name='yolo_loss',
        arguments={'anchors': anchors, 'num_classes': num_classes, 'ignore_thresh': 0.5})(
        [*model_body.output, *y_true])
    model = Model([model_body.input, *y_true], model_loss)
    print('model_body.input: ', model_body.input)
    print('model.input: ', model.input)

    return model

def create_tiny_model(input_shape, anchors, num_classes, load_pretrained=True, freeze_body=2,
            weights_path='model_data/tiny_yolo_weights.h5'):
    '''create the training model, for Tiny YOLOv3'''
    K.clear_session() # get a new session
    image_input = Input(shape=(None, None, 3))
    h, w = input_shape
    num_anchors = len(anchors)

    y_true = [Input(shape=(h//{0:32, 1:16}[l], w//{0:32, 1:16}[l], \
        num_anchors//2, num_classes+5)) for l in range(2)]

    model_body = tiny_yolo_body(image_input, num_anchors//2, num_classes)
    print('Create Tiny YOLOv3 model with {} anchors and {} classes.'.format(num_anchors, num_classes))
    if load_pretrained:
        model_body.load_weights(weights_path, by_name=True, skip_mismatch=True)
        print('Load weights {}.'.format(weights_path))
        if freeze_body in [1, 2]:
            # Freeze the darknet body or freeze all but 2 output layers.
            num = (20, len(model_body.layers)-2)[freeze_body-1]
            for i in range(num): model_body.layers[i].trainable = False
            print('Freeze the first {} layers of total {} layers.'.format(num, len(model_body.layers)))

    model_loss = Lambda(yolo_loss, output_shape=(1,), name='yolo_loss',
        arguments={'anchors': anchors, 'num_classes': num_classes, 'ignore_thresh': 0.7})(
        [*model_body.output, *y_true])
    model = Model([model_body.input, *y_true], model_loss)

    return model

def data_generator(annotation_lines, batch_size, input_shape, anchors, num_classes):
    '''data generator for fit_generator'''
    n = len(annotation_lines)
    i = 0
    while True:
        image_data = []
        box_data = []
        for b in range(batch_size):
            if i==0:
                np.random.shuffle(annotation_lines)
            image, box = get_random_data(annotation_lines[i], input_shape, random=True)
            image_data.append(image)
            box_data.append(box)
            i = (i+1) % n
        image_data = np.array(image_data)   # input of original yolo: image
        box_data = np.array(box_data)       # output of original yolo: boxes
        y_true = preprocess_true_boxes(box_data, input_shape, anchors, num_classes) # some kind of output description?!
        yield [image_data, *y_true], np.zeros(batch_size)

def data_generator_wrapper(annotation_lines, batch_size, input_shape, anchors, num_classes):
    n = len(annotation_lines)
    if n==0 or batch_size<=0: return None
    return data_generator(annotation_lines, batch_size, input_shape, anchors, num_classes)

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser()

    parser.add_argument("-a", "--annotation_path", type=str, default='/home/madiou/Documents/A-Baamtu/learning_step/ob_detect/Eau/data_w_aug/dataset_aug_info.txt', help="input annotation_path")
    parser.add_argument("-c", "--classes_path", type=str, default='/home/madiou/Documents/A-Baamtu/learning_step/ob_detect/Eau/data_w_aug/classes_name_water_invoices.txt', help="input classes_path")
    parser.add_argument("-o", "--output_model_path", type=str, default='/home/madiou/Documents/A-Baamtu/learning_step/ob_detect/Eau/output/output_model_weights_water.h5', help="input output_model_path")
    args = parser.parse_args()
    print('annotation_path = ', args.annotation_path)
    print('classes_path = ', args.classes_path)
    print('output_model_path = ', args.output_model_path)

    _main(args.annotation_path, args.classes_path, args.output_model_path)


