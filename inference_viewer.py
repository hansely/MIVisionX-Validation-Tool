import pyqtgraph as pg
import cv2
import numpy as np
from PyQt4 import QtGui, uic, QtCore
from PyQt4.QtGui import QPixmap
from PyQt4.QtCore import QTime, QTimer
from inference_setup import *
from rali_setup import *

class InferenceViewer(QtGui.QMainWindow):
    def __init__(self, model_name, model_format, image_dir, model_location, label, hierarchy, image_val, input_dims, output_dims, 
                                    batch_size, output_dir, add, multiply, verbose, fp16, replace, loop, rali_mode, container_logo, parent=None):
        super(InferenceViewer, self).__init__(parent)

        self.model_name = model_name
        self.model_format = model_format 
        self.image_dir = image_dir
        self.model_location = model_location
        self.label = label
        self.hierarchy = hierarchy
        self.image_val = image_val
        self.input_dims = input_dims
        self.output_dims = output_dims
        self.batch_size = batch_size
        self.batch_size_int = (int)(batch_size)
        self.output_dir = output_dir
        self.add = add
        self.multiply = multiply
        self.verbose = verbose
        self.fp16 = fp16
        self.replace = replace
        self.loop = loop
        self.rali_mode = rali_mode
        inputImageDir = os.path.expanduser(image_dir)
        self.total_images = len(os.listdir(inputImageDir))
        self.imgCount = 0
        self.frameCount = 9
        self.container_index = (int)(container_logo)
        # self.origImageQueue = Queue.Queue()
        # self.augImageQueue = Queue.Queue()
        str_c_i, str_h_i, str_w_i = input_dims.split(',')
        self.c_i = int(str_c_i); self.h_i = int(str_h_i); self.w_i = int(str_w_i)
        str_c_o, str_h_o, str_w_o = output_dims.split(',')
        self.c_o = int(str_c_o); self.h_o = int(str_h_o); self.w_o = int(str_w_o)
        self.Ax=[0,0,0]
        if(add != ''):
			self.Ax = [float(item) for item in add.strip("[]").split(',')]
        self.Mx=[1,1,1]
        if(multiply != ''):
			self.Mx = [float(item) for item in multiply.strip("[]").split(',')]

        self.graph = pg.PlotWidget(title="Accuracy vs Time")
        self.x = [0] 
        self.y = [0]
        self.augAccuracy = []
        
        self.time = QTime.currentTime()

        self.runState = False
        self.pauseState = False
        self.progIndex = 0
        self.augIntensity = 0.0
        self.lastIndex = self.frameCount - 1

        self.pen = pg.mkPen('w', width=4)

        self.raliEngine = None
        self.inferenceEngine = None
        self.raliList = []
        self.labelNames = []

        self.AMD_Radeon_pixmap = QPixmap("./data/images/AMD_Radeon.png")
        self.AMD_Radeon_white_pixmap = QPixmap("./data/images/AMD_Radeon-white.png")
        self.MIVisionX_pixmap = QPixmap("./data/images/MIVisionX-logo.png")
        self.MIVisionX_white_pixmap = QPixmap("./data/images/MIVisionX-logo-white.png")
        self.EPYC_pixmap = QPixmap("./data/images/EPYC-blue.png")
        self.EPYC_white_pixmap = QPixmap("./data/images/EPYC-blue-white.png")
        self.docker_pixmap = QPixmap("./data/images/Docker.png")
        self.singularity_pixmap = QPixmap("./data/images/Singularity.png")

        self.initUI()
        #self.show()
        self.initEngines()
        self.run()
        
        updateTimer = QTimer()
        #QTimer.connect(self.timer, QtCore.SIGNAL("timeout()"), self, QtCore.SLOT("update()"))

        #updateTimer.timeout.connect(self.update)
        updateTimer.start(40)

    def initUI(self):
        uic.loadUi("inference_viewer.ui", self)
        #self.showMaximized()
        self.setStyleSheet("background-color: white")
        self.name_label.setText("Model: %s" % (self.model_name))
        self.dataset_label.setText("Augmentation set - %d" % (self.rali_mode))
        self.imagesFrame.setStyleSheet(".QFrame {border-width: 20px; border-image: url(./data/images/filmStrip.png);}")
        self.total_progressBar.setStyleSheet("QProgressBar::chunk { background: lightblue; }")
        self.top1_progressBar.setStyleSheet("QProgressBar::chunk { background: green; }")
        self.top5_progressBar.setStyleSheet("QProgressBar::chunk { background: lightgreen; }")
        self.mis_progressBar.setStyleSheet("QProgressBar::chunk { background: red; }")
        self.total_progressBar.setMaximum(self.total_images*self.batch_size_int)

        self.graph.setLabel('left', 'Accuracy', '%')
        self.graph.setLabel('bottom', 'Time', 's')
        self.graph.setYRange(0, 100, padding=0)
        #self.graph.addLegend()
        self.graph.plot(self.x, self.y, pen=self.pen, name='Total')
        self.verticalLayout_2.addWidget(self.graph)
        self.graph.setBackground(None)
        self.graph.setMaximumWidth(550)
        self.graph.setMaximumHeight(300)
        self.level_slider.setMaximum(100)
        self.level_slider.valueChanged.connect(self.setIntensity)
        self.pause_pushButton.setStyleSheet("color: white; background-color: darkBlue")
        self.stop_pushButton.setStyleSheet("color: white; background-color: darkRed")
        self.pause_pushButton.clicked.connect(self.pauseView)
        self.stop_pushButton.clicked.connect(self.closeView)
        self.dark_checkBox.stateChanged.connect(self.setBackground)
        self.verbose_checkBox.stateChanged.connect(self.showVerbose)
        self.dark_checkBox.setChecked(True)

        if self.container_index == 1:
            self.container_logo.setPixmap(self.docker_pixmap)
        elif self.container_index == 2:
            self.container_logo.setPixmap(self.singularity_pixmap)
        else:
            self.container_logo.hide()

        for augmentation in range(self.batch_size_int):
            self.augAccuracy.append([0])

        self.showVerbose()

    def resetViewer(self):
        self.imgCount = 0
        del self.x[:]
        self.x.append(0)
        del self.y[:]
        self.y.append(0)
        del self.augAccuracy[:]
        for augmentation in range(self.batch_size_int):
            self.augAccuracy.append([0])

        self.time = QTime.currentTime()
        self.lastTime = 0
        self.progIndex = 0
        self.lastIndex = self.frameCount - 1
        self.graph.clear()

    def setTotalProgress(self, value):
        self.total_progressBar.setValue(value)
        if self.getIndex() == 0:
            self.total_progressBar.setMaximum(self.total_images*self.batch_size)
            self.imgProg_label.setText("Processed: %d of %d" % (value, self.total_images*self.batch_size))
        else:
            self.total_progressBar.setMaximum(self.total_images)
            self.imgProg_label.setText("Processed: %d of %d" % (value, self.total_images))
    
    def setTop1Progress(self, value, total):
        self.top1_progressBar.setValue(value)
        self.top1_progressBar.setMaximum(total)
    
    def setTop5Progress(self, value, total):
        self.top5_progressBar.setValue(value)
        self.top5_progressBar.setMaximum(total)
    
    def setMisProgress(self, value, total):
        self.mis_progressBar.setValue(value)
        self.mis_progressBar.setMaximum(total)
    
    # def setNoGTProgress(self, value):
    #     self.noGT_progressBar.setValue(value)

    def plotGraph(self, accuracy):
        curTime = self.time.elapsed()/1000.0
        if (curTime - self.lastTime > 0.1):
            self.x.append(curTime)
            self.y.append(accuracy)
            self.graph.plot(self.x, self.y, pen=self.pen)
            if self.progIndex:
                self.graph.plot(self.x, self.augAccuracy[self.progIndex-1], pen=pg.mkPen('b', width=4))
            self.lastTime = curTime

    def showImage(self, image, width, height):
        qimage = QtGui.QImage(image, width, height, width*3, QtGui.QImage.Format_RGB888)
        qimage_resized = qimage.scaled(self.image_label.width(), self.image_label.height(), QtCore.Qt.IgnoreAspectRatio)
        index = self.imgCount % self.frameCount
        self.origImage_layout.itemAt(index).widget().setPixmap(QtGui.QPixmap.fromImage(qimage_resized))
        self.origImage_layout.itemAt(index).widget().setStyleSheet("border: 5px solid yellow;");
        self.origImage_layout.itemAt(self.lastIndex).widget().setStyleSheet("border: 0");
        self.imgCount += 1
        self.lastIndex = index

    def showAugImage(self, image, width, height):
        qimage = QtGui.QImage(image, width, height, width*3, QtGui.QImage.Format_RGB888)
        if self.batch_size == 64:
            qimage_resized = qimage.scaled(self.aug_label.width(), self.aug_label.height(), QtCore.Qt.IgnoreAspectRatio)
        elif self.batch_size == 16:
            qimage_resized = qimage.scaled(self.aug_label.width(), self.aug_label.height(), QtCore.Qt.KeepAspectRatio)
        pixmap = QtGui.QPixmap.fromImage(qimage_resized)
        self.aug_label.setPixmap(pixmap)

    # def putAugImage(self, image, width, height):
    #     qimage = QtGui.QImage(image, width, height, width*3, QtGui.QImage.Format_RGB888)
    #     qimage_resized = qimage.scaled(self.aug_label.width(), self.aug_label.height(), QtCore.Qt.KeepAspectRatio)
    #     pixmap = QtGui.QPixmap.fromImage(qimage_resized)
    #     self.augImageQueue.put(pixmap)

    # def putImage(self, image, width, height):
    #     qimage = QtGui.QImage(image, width, height, width*3, QtGui.QImage.Format_RGB888)
    #     qimage_resized = qimage.scaled(self.image_label.width(), self.image_label.height(), QtCore.Qt.KeepAspectRatio)
    #     pixmap = QtGui.QPixmap.fromImage(qimage_resized)
    #     self.origImageQueue.put(pixmap)

    # def showImage(self):
    #     if not self.origImageQueue.empty():
    #         origImage = self.origImageQueue.get()
    #         augImage = self.augImageQueue.get()
    #         self.imageList[(self.imgCount % self.frameCount)].setPixmap(origImage)
    #         self.aug_label.setPixmap(augImage)
    #         self.imgCount += 1

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.closeView()
            
        if event.key() == QtCore.Qt.Key_Space:
            self.pauseView()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            mousePos = event.pos()
            if self.aug_label.geometry().contains(mousePos):
                index = self.calculateIndex(mousePos.x(), mousePos.y())
                self.progIndex = index
            else:
                self.progIndex = 0
            
            self.graph.clear()

    def setBackground(self):
        if self.dark_checkBox.isChecked():
            self.setStyleSheet("background-color: #25232F;")
            self.pen = pg.mkPen('w', width=4)
            self.graph.setBackground(None)
            self.origTitle_label.setStyleSheet("color: #C82327;")
            self.controlTitle_label.setStyleSheet("color: #C82327;")
            self.progTitle_label.setStyleSheet("color: #C82327;")
            self.graphTitle_label.setStyleSheet("color: #C82327;")
            self.augTitle_label.setStyleSheet("color: #C82327;")
            self.name_label.setStyleSheet("color: white;")
            self.dataset_label.setStyleSheet("color: white;")
            self.imgProg_label.setStyleSheet("color: white;")
            self.fps_label.setStyleSheet("color: #C82327;")
            self.dark_checkBox.setStyleSheet("color: white;")
            self.verbose_checkBox.setStyleSheet("color: white;")
            self.level_label.setStyleSheet("color: white;")
            self.low_label.setStyleSheet("color: white;")
            self.high_label.setStyleSheet("color: white;")
            self.AMD_logo.setPixmap(self.AMD_Radeon_white_pixmap)
            self.MIVisionX_logo.setPixmap(self.MIVisionX_white_pixmap)
            self.EPYC_logo.setPixmap(self.EPYC_white_pixmap)
        else:
            self.setStyleSheet("background-color: white;")
            self.pen = pg.mkPen('k', width=4)
            self.graph.setBackground(None)
            self.origTitle_label.setStyleSheet("color: 0;")
            self.controlTitle_label.setStyleSheet("color: 0;")
            self.progTitle_label.setStyleSheet("color: 0;")
            self.graphTitle_label.setStyleSheet("color: 0;")
            self.augTitle_label.setStyleSheet("color: 0;")
            self.name_label.setStyleSheet("color: 0;")
            self.dataset_label.setStyleSheet("color: 0;")
            self.imgProg_label.setStyleSheet("color: 0;")
            self.fps_label.setStyleSheet("color: 0;")
            self.dark_checkBox.setStyleSheet("color: 0;")
            self.verbose_checkBox.setStyleSheet("color: 0;")
            self.level_label.setStyleSheet("color: 0;")
            self.low_label.setStyleSheet("color: 0;")
            self.high_label.setStyleSheet("color: 0;")
            self.AMD_logo.setPixmap(self.AMD_Radeon_pixmap)
            self.MIVisionX_logo.setPixmap(self.MIVisionX_pixmap)
            self.EPYC_logo.setPixmap(self.EPYC_pixmap)
            
    def showVerbose(self):
        if self.verbose_checkBox.isChecked():
            self.dataset_label.show()
            self.fps_label.show()
            self.fps_lcdNumber.show()
        else:
            self.dataset_label.hide()
            self.fps_label.hide()
            self.fps_lcdNumber.hide()
        
    def displayFPS(self, fps):
        self.fps_lcdNumber.display(fps)

    def pauseView(self):
        self.pauseState = not self.pauseState
        if self.pauseState:
            self.pause_pushButton.setText('Resume')
        else:
            self.pause_pushButton.setText('Pause')

    def closeView(self):
        self.runState = False

    def startView(self):
        self.runState = True

    def stopView(self):
        self.runState = False

    def getState(self):
        return self.runState

    def isPaused(self):
        return self.pauseState

    def setIntensity(self):
        self.augIntensity = (float)(self.level_slider.value()) / 100.0

    def getIntensity(self):
        return self.augIntensity

    def calculateIndex(self, x, y):
        if self.batch_size == 64:
            imgWidth = self.aug_label.width() / 16.0
        else:
            imgWidth = self.aug_label.width() / 4.0
        imgHeight = self.aug_label.height() / 4.0
        x -= self.aug_label.x()
        y -= self.aug_label.y()
        column = (int)(x / imgWidth)
        row = (int)(y / imgHeight)
        index = 4 * column + row
        return index + 1

    def getIndex(self):
        return self.progIndex
    
    def setAugName(self, name):
        self.name_label.setText(name)

    def storeAccuracy(self, index, accuracy):
        curTime = self.time.elapsed()/1000.0
        if (curTime - self.lastTime > 0.1):
            self.augAccuracy[index].append(accuracy)

    def initEngines(self):
        # Creating an object for inference. Input arguments come from the user
        self.inferenceEngine = modelInference(self.model_name, self.model_format, self.image_dir, self.model_location, self.label, self.hierarchy, self.image_val,
                                                self.input_dims, self.output_dims, self.batch_size, self.output_dir, self.add, self.multiply, self.verbose, self.fp16, 
                                                self.replace, self.loop)
        
        # caffe/onnx to openvx and runs anntest. Also creates empty file for ADAT
        inputImageDir, totalImages, imageValidation, self.labelNames = self.inferenceEngine.setupInference()

        # Setup Rali Data Loader. 
        rali_batch_size = 1
        self.raliEngine = DataLoader(inputImageDir, rali_batch_size, int(self.batch_size), ColorFormat.IMAGE_RGB24, Affinity.PROCESS_CPU, imageValidation, self.h_i, self.w_i, self.rali_mode, self.loop, 
                                        TensorLayout.NCHW, False, self.Ax, self.Mx)
        
        # get correct list for augmentations
        self.raliList = self.raliEngine.get_rali_list(self.rali_mode, int(self.batch_size))
        
    def run(self):

        # update parameters for the augmentation & get 64 augmentations for an image
        augmentation = self.getIntensity()
        self.raliEngine.updateAugmentationParameter(augmentation)

        image_batch, image_tensor = self.raliEngine.get_next_augmentation()
        frame = image_tensor
        original_image = image_batch[0:self.h_i, 0:self.w_i]
        cloned_image = np.copy(image_batch)
        
        #get image file name and ground truth
        imageFileName = self.raliEngine.get_input_name()
        groundTruthIndex = self.raliEngine.get_ground_truth()
        groundTruthIndex = int(groundTruthIndex)

        # draw box for original image and put label
        groundTruthLabel = self.labelNames[groundTruthIndex].decode("utf-8").split(' ', 1)
        text_width, text_height = cv2.getTextSize(groundTruthLabel[1].split(',')[0], cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
        text_off_x = (self.w_i/2) - (text_width/2)
        text_off_y = self.h_i-7
        box_coords = ((text_off_x, text_off_y), (text_off_x + text_width - 2, text_off_y - text_height - 2))
        cv2.rectangle(original_image, box_coords[0], box_coords[1], (245, 197, 66), cv2.FILLED)
        cv2.putText(original_image, groundTruthLabel[1].split(',')[0], (text_off_x, text_off_y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,0), 2)

        #Step 7: call python inference. Returns output tensor with 1000 class probabilites
        output = self.inferenceEngine.inference(frame)
        
        #Step 8: Process output for each of the 64 images
        for i in range(self.raliEngine.getOutputImageCount()):
            topIndex, topProb = self.inferenceEngine.processClassificationOutput(output)

            correctTop5 = 0; correctTop1 = 0; wrong = 0; noGroundTruth = 0;
            #create output dict for all the images
            guiResults = {}
            #to calculate FPS
            avg_benchmark = 0.0
            frameMsecs = 0.0
            frameMsecsGUI = 0.0
            totalFPS = 0.0
            resultPerAugmentation = []
            for iterator in range(self.batch_size_int):
                resultPerAugmentation.append([0,0,0])

            #create output list for each image
            augmentedResults = []

            #process the output tensor
            resultPerAugmentation, augmentedResults = self.inferenceEngine.processOutput(correctTop1, correctTop5, augmentedResults, resultPerAugmentation, groundTruthIndex,
                                                                                         topIndex, topProb, wrong, noGroundTruth, i)

            augmentationText = self.raliList[i].split('+')
            textCount = len(augmentationText)
            for cnt in range(0,textCount):
                currentText = augmentationText[cnt]
                text_width, text_height = cv2.getTextSize(currentText, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)[0]
                text_off_x = (w_i/2) - (text_width/2)
                text_off_y = (i*h_i)+h_i-7-(cnt*text_height)
                box_coords = ((text_off_x, text_off_y), (text_off_x + text_width - 2, text_off_y - text_height - 2))
                cv2.rectangle(cloned_image, box_coords[0], box_coords[1], (245, 197, 66), cv2.FILLED)
                cv2.putText(cloned_image, currentText, (text_off_x, text_off_y), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,0,0), 2) 

            # put augmented image result
            if augmentedResults[i] == 0:
                cv2.rectangle(cloned_image, (0,(i*(h_i-1)+i)),((w_i-1),(h_i-1)*(i+1) + i), (255,0,0), 4, cv2.LINE_8, 0)
            elif augmentedResults[i] > 0  and augmentedResults[i] < 6:      
                    cv2.rectangle(cloned_image, (0,(i*(h_i-1)+i)),((w_i-1),(h_i-1)*(i+1) + i), (0,255,0), 4, cv2.LINE_8, 0)

        #Step 9: split image as needed
        if int(modelBatchSize) == 64:
                image_batch = np.vsplit(cloned_image, 16)
                final_image_batch = np.hstack((image_batch))
        elif int(modelBatchSize) == 16:
            image_batch = np.vsplit(cloned_image, 4)
            final_image_batch = np.hstack((image_batch))

        #Step 10: adat generation
        if adatFlag == False:
            self.raliEngine.generateADAT(modelName, hierarchy)
            adatFlag = True
