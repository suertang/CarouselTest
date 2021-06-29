# -*- coding: utf-8 -*-
"""
Created on Wed Apr 11 10:42:35 2018

@author: jeff.gu@thermofisher.com
@adapted by Zhongji.tang@thermofisher.com
"""
import os
import sys
import cv2
import math
import numpy as np


class CalcDistance:
    def __init__(self, raw_image=None, filename=None, bOutImage=False):
        # VERY IMPORTANT NOTE: H range is from 0~179, but not 0~255
        # Green Color Range in HSV space, it is a value after experiment
        self.low_green = np.array([40, 70, 100], dtype=np.uint8)
        self.up_green = np.array([80, 240, 240], dtype=np.uint8)
        # Red Color Range in HSV space, it is a value after experiment
        self.low_red1 = np.array([0, 30, 128])
        self.up_red1 = np.array([20, 255, 255])
        self.low_red2 = np.array([175, 60, 128])
        self.up_red2 = np.array([179, 150, 255])



# if len(sys.argv) != 3:
#     print("Format: %s filePath generateImage(0/1)" %(sys.argv[0]))
#     sys.exit(0)

        self.filename = filename
        self.bOutputImage = bOutImage
        #filename = "12012001_674_17.4.png"
        if raw_image is None:
            self.im_orig = cv2.imread(filename)
        else:
            self.im_orig = raw_image
    #Used to get the center point of a cross with specific color
    def getCenterOfLine(self, image, colormask, lengthTh):
        im = image
        # Filter out specific color image
        im = cv2.bitwise_and(im, im, mask=colormask)
    #    cv2.imshow("ColorFilterImage",im)
    #    cv2.waitKey(0)

        # Get Black and whilte Figure which has clear edge
        im = cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
        im = cv2.GaussianBlur(im,(13,13),1.4,1.4)
        thres,im = cv2.threshold(im,0,255,cv2.THRESH_OTSU)
    #    cv2.imshow("BWImage",im)
    #    cv2.waitKey(0)

        # Get the edges
        edges = cv2.Canny(im, 50, 150, apertureSize = 3)
    #    cv2.imshow("EdgeImage",edges)
    #    cv2.waitKey(0)

        # get lines in edges, with propr threshold, all the lines should be available now
        lines = cv2.HoughLinesP(edges, 1, np.pi/180,10,minLineLength=lengthTh-3,maxLineGap=3)
        if lines is None:
            return 0

        lines2D = lines[:, 0, :]  # 3D to 2D
        # print("Line Number:",len(lines2D))
        # for x1,y1,x2,y2 in lines2D[:]:
        #    cv2.line(image,(x1,y1),(x2,y2),(0,0,255),1)

        min_x = 1000
        max_x = 0
        for line in lines2D:
            if min_x > line[0]:
                min_x = line[0]
            if max_x <line[0]:
                max_x = line[0]

        return ((min_x+max_x)/2)

    def process(self):

        #im_orig = cv2.imread("a6.png")

        # Crop the center of Image to
        # .reduce the calculation amount
        # .remove the interfere object including cursor edge
        # .avoid side effect of camera lens distortion
        im = self.im_orig[100:280,220:391]   #y_start:420, y_end:820, x_start:730,x_end:1130

        #cv2.imshow("CropImage",im)
        #cv2.waitKey(0)

        # change to hsv model
        hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
        # get mask
        maskG = cv2.inRange(hsv, self.low_green, self.up_green)
        maskR1 = cv2.inRange(hsv, self.low_red1, self.up_red1)
        maskR2 = cv2.inRange(hsv, self.low_red2, self.up_red2)
        maskR = cv2.addWeighted(maskR1, 1.0, maskR2, 1.0, 0.0)

        #cv2.imshow("CropColorImage",im)
        #cv2.waitKey(0)

        xRed = self.getCenterOfLine(im, maskR, 20)
        xRed += 220
        # print('x:',xRed)

        xGreen = self.getCenterOfLine(im, maskG, 15)
        xGreen += 220
        # print('x2:',xGreen)
        if xRed is 220 or xGreen is 220:
            Distance = 0
        else:
            Distance = xRed - xGreen
            cv2.line(self.im_orig, (xRed, 180), (xGreen, 180), (0, 0, 255), 3)

        # print("Result:", Distance)


        #cv2.imshow("FinalResult",im_orig)
        #cv2.waitKey(0)

        if self.bOutputImage and self.filename is not None:
            outputName = self.filename[:-4] + "_calc.jpg"
            cv2.imwrite(outputName, self.im_orig)

        cv2.destroyAllWindows()
        return Distance


if __name__ == '__main__':
    camera = cv2.VideoCapture(0)
    return_value, image = camera.read()
    print(return_value)
    path = os.path.abspath('./')
    print(path)
    cv2.imwrite(os.path.join(path, 'cc.jpg'), image)

    c = CalcDistance(image)
    print(c.process())
