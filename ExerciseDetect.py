# -*- coding: utf-8 -*-
import argparse
import time
from pathlib import Path
import cv2
import torch
import torch.backends.cudnn as cudnn
from numpy import random
from models.experimental import attempt_load
from utils.datasets import LoadStreams, LoadImages
from utils.general import check_img_size, check_requirements, check_imshow, non_max_suppression, apply_classifier, \
    scale_coords, xyxy2xywh, strip_optimizer, set_logging, increment_path
from utils.plots import plot_one_box
from utils.torch_utils import select_device, load_classifier, time_synchronized
from PaddleOCR import PaddleOCR
import os
from flask import Flask, request, send_from_directory
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'images/'
app.config['DOWNLOAD_FOLDER'] = 'runs/detect/result'

@app.route('/exerciseDetect/', methods=['POST'])
def exerciseDetect():
    print('收到POST请求')
    try:
        f = request.files['imgFile']
        filename = secure_filename(f.filename)
        imgPath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        f.save(imgPath)
        msg = ""
        statusCode = 1 # 0-检测到题目，1-没有检测到题目，-1-下载文件失败
        if Detection(imgPath):
            msg = Recognition(imgPath)
            statusCode = 0
        else:
            msg = "该图片没有检测到题目"
        {
            'statusCode': statusCode,
            'msg': msg,
            'filename': filename
        }

        res =         res2Json = json.dumps(res,ensure_ascii=False)
        print(res2Json)
        return res2Json
    except Exception:
        res = {
            'statusCode': -1,
            'msg': '服务器下载文件失败'
        }
        res2Json = json.dumps(res, ensure_ascii=False)
        print(res2Json)
        return res2Json

@app.route('/downloadImage/<filename>', methods=['GET'])
def downloadImage(filename):
    print('收到GET请求')
    print('客户端请求下载的文件名：'+filename)
    try:
        return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)
    except Exception:
        return 'error', 400

def Recognition(imgPath):
    filename = imgPath.split('/')[-1].split('.')[0]

    f = open('runs/detect/result/labels/'+ filename +'_box.txt', 'r')
    titleBoxs = []
    lines = f.readlines()
    for line in lines:
        titleBox = line.strip("\n").split(" ")
        titleBoxs.append(titleBox)

    # 将题目框按高度从上到下排序
    def takeSecond(elem):
        return int(elem[1]) # 根据嵌套列表中的第二项转成int进行排序
    titleBoxs.sort(reverse = False,key=takeSecond)

    # 识别文字，改GPU,CPU
    ocr = PaddleOCR(use_angle_cls=True, use_gpu=False)

    resultText = ''
    i = 0
    img = cv2.imread(imgPath)
    # 剪裁题目区域
    for titleBox in titleBoxs:
        i = i + 1
        titleText = ""
        titleImg = img[int(titleBox[1]):int(titleBox[3]), int(titleBox[0]):int(titleBox[2])]  # 裁剪坐标为[y0:y1, x0:x1]
        result = ocr.ocr(titleImg, cls=True)
        for line in result:
            titleText = titleText + line[1][0]
        resultText = resultText + '题目{}:'.format(i) + '\n'
        resultText = resultText + titleText + '\n\n'

    print(resultText)
    return resultText

def Detection(filePath):
    # weights: 训练的权重
    # source: 测试数据，可以是图片/视频路径，也可以是'0'(电脑自带摄像头), 也可以是rtsp等视频流
    # img-size: 网络输入图片大小
    # conf-thres: 置信度阈值
    # iou-thres: 做nms的iou阈值
    # device: 设置设备
    # view-img: 是否展示预测之后的图片/视频，默认False
    # save-txt: 是否将预测的框坐标以txt文件形式保存，默认False
    # save-conf: 是否保存置信度到上述txt文件中，默认False
    # nosave: 是否保存图片/视频
    # classes: 设置只保留某一部分类别，形如0或者0 2 3
    # agnostic-nms: 进行nms是否也去除不同类别之间的框，默认False
    # augment: 推理的时候进行多尺度，翻转等操作(TTA)推理
    # update: 如果为True，则对所有模型进行strip_optimizer操作，去除pt文件中的优化器等信息，默认为False

    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', nargs='+', type=str, default='weights/best.pt', help='model.pt path(s)')
    parser.add_argument('--source', type=str, default=filePath, help='source')  # file/folder, 0 for webcam
    parser.add_argument('--img-size', type=int, default=640, help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--device', default='cpu', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', action='store_true', help='display results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--nosave', action='store_true', help='do not save images/videos')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default='runs/detect', help='save results to project/name')
    parser.add_argument('--name', default='result', help='save results to project/name')
    parser.add_argument('--exist-ok', default=' ', action='store_true', help='existing project/name ok, do not increment')
    opt = parser.parse_args()
    print(opt)
    check_requirements(exclude=('pycocotools', 'thop'))

    with torch.no_grad():
        if opt.update:  # update all models (to fix SourceChangeWarning)
            for opt.weights in ['yolov5s.pt', 'yolov5m.pt', 'yolov5l.pt', 'yolov5x.pt']:
                if detect(opt):
                    strip_optimizer(opt.weights)
                    return True
                else:
                    return False
        else:
            if detect(opt):
                return True
            else:
                return False

def detect(opt, save_img=False):
    # 获取输出文件夹，输入源，权重等参数
    source, weights, view_img, save_txt, imgsz = opt.source, opt.weights, opt.view_img, opt.save_txt, opt.img_size
    save_img = not opt.nosave and not source.endswith('.txt')  # save inference images
    webcam = source.isnumeric() or source.endswith('.txt') or source.lower().startswith(
        ('rtsp://', 'rtmp://', 'http://'))

    # Directories
    save_dir = Path(increment_path(Path(opt.project) / opt.name, exist_ok=opt.exist_ok))  # increment run
    (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    # Initialize
    set_logging()
    device = select_device(opt.device)
    # 如果设备为gpu，使用Float16
    half = device.type != 'cpu'  # half precision only supported on CUDA

    # Load model
    # 加载Float32模型，确保用户设定的输入图片分辨率能整除32(如不能则调整为能整除并返回)
    model = attempt_load(weights, map_location=device)  # load FP32 model
    stride = int(model.stride.max())  # model stride
    imgsz = check_img_size(imgsz, s=stride)  # check img_size
    if half:
        model.half()  # to FP16

    # Second-stage classifier
    # 设置第二次分类，默认不使用
    classify = False
    if classify:
        modelc = load_classifier(name='resnet101', n=2)  # initialize
        modelc.load_state_dict(torch.load('weights/resnet101.pt', map_location=device)['model']).to(device).eval()

    # Set Dataloader
    # 通过不同的输入源来设置不同的数据加载方式
    vid_path, vid_writer = None, None
    if webcam:
        view_img = check_imshow()
        cudnn.benchmark = True  # set True to speed up constant image size inference
        dataset = LoadStreams(source, img_size=imgsz, stride=stride)
    else:
        # 如果检测视频的时候想显示出来，可以在这里加一行view_img = True
        # view_img = True
        dataset = LoadImages(source, img_size=imgsz, stride=stride)

    # Get names and colors
    # 获取类别名字
    names = model.module.names if hasattr(model, 'module') else model.names
    # 设置画框的颜色
    #colors = [[random.randint(0, 255) for _ in range(3)] for _ in names]
    colors =[[227, 173, 28]] # 设置颜色固定（此颜色为蓝色，与RBG色值不同，）
    #print("color = ", end="")
    #print(colors)

    # Run inference
    if device.type != 'cpu':
        # 进行一次前向推理,测试程序是否正常
        model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(next(model.parameters())))  # run once
    t0 = time.time()

    # path 图片/视频路径
    # img 进行resize+pad之后的图片
    # img0 原size图片
    # cap 当读取图片时为None，读取视频时为视频源
    for path, img, im0s, vid_cap in dataset:
        img = torch.from_numpy(img).to(device)
        img = img.half() if half else img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if img.ndimension() == 3:
            img = img.unsqueeze(0)

        # Inference
        t1 = time_synchronized()

        # 前向传播
        # 返回pred的shape是(1, num_boxes, 5 + num_class)
        # h, w为传入网络图片的长和宽，注意dataset在检测时使用了矩形推理，所以这里h不一定等于w
        # num_boxes = h / 32 * w / 32 + h / 16 * w / 16 + h / 8 * w / 8
        # pred[..., 0:4]为预测框坐标
        # 预测框坐标为xywh(中心点 + 宽长)格式
        # pred[..., 4]为objectness置信度
        # pred[..., 5:-1]为分类结果
        pred = model(img, augment=opt.augment)[0]

        # Apply NMS
        # pred: 前向传播的输出
        # conf_thres: 置信度阈值
        # iou_thres: iou阈值
        # classes: 是否只保留特定的类别
        # agnostic: 进行nms是否也去除不同类别之间的框
        # 经过nms之后，预测框格式：xywh -->xyxy(左上角右下角)
        # pred是一个列表list[torch.tensor]，长度为batch_size
        # 每一个torch.tensor的shape为(num_boxes, 6), 内容为box + conf + cls
        pred = non_max_suppression(pred, opt.conf_thres, opt.iou_thres, classes=opt.classes, agnostic=opt.agnostic_nms)
        t2 = time_synchronized()

        # Apply Classifier
        # 添加二次分类，默认不使用
        if classify:
            pred = apply_classifier(pred, modelc, img, im0s)

        # Process detections
        # 对每一张图片作处理
        for i, det in enumerate(pred):  # detections per image
            # 如果输入源是webcam，则batch_size不为1，取出dataset中的一张图片
            if webcam:  # batch_size >= 1
                p, s, im0, frame = path[i], '%g: ' % i, im0s[i].copy(), dataset.count
            else:
                p, s, im0, frame = path, '', im0s, getattr(dataset, 'frame', 0)

            # 设置保存图片/视频的路径
            p = Path(p)  # to Path
            save_path = str(save_dir / p.name)  # img.jpg
            # 设置保存框坐标txt文件的路径
            txt_path = str(save_dir / 'labels' / p.stem) + ('' if dataset.mode == 'image' else f'_{frame}')  # img.txt
            # 设置打印信息(图片长宽)
            s += '%gx%g ' % img.shape[2:]  # print string
            gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh
            if len(det):
                # Rescale boxes from img_size to im0 size
                # 调整预测框的坐标：基于resize+pad的图片的坐标-->基于原size图片的坐标
                # 此时坐标格式为xyxy
                det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()

                # Print results
                # 打印检测到的类别数量
                for c in det[:, -1].unique():
                    n = (det[:, -1] == c).sum()  # detections per class
                    s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string

                # Write results
                # 进循环前先检测储存预测框文件存不存在，如果文件存在，先删除该文件，避免重复写入
                box_file = txt_path + '_box.txt'
                if os.path.exists(box_file):
                    os.remove(box_file)
                for *xyxy, conf, cls in reversed(det):

                    if save_txt:  # Write to file
                        # 将xyxy(左上角+右下角)格式转为xywh(中心点+宽长)格式，并除上w，h做归一化，转化为列表再保存
                        xywh = (xyxy2xywh(torch.tensor(xyxy).view(1, 4)) / gn).view(-1).tolist()  # normalized xywh
                        line = (cls, *xywh, conf) if opt.save_conf else (cls, *xywh)  # label format
                        with open(txt_path + '.txt', 'a') as f:
                            f.write(('%g ' * len(line)).rstrip() % line + '\n')

                    # 在原图上画框
                    if save_img or view_img:  # Add bbox to image
                        label = f'{names[int(cls)]} {conf:.2f}'
                        plot_one_box(xyxy, im0, label=label, color=colors[int(cls)], line_thickness=3)

                        # 储存预测框的坐标信息
                        with open(box_file, 'a') as f:
                            f.write('{} {} {} {}\n'.format(int(xyxy[0]),int(xyxy[1]),int(xyxy[2]),int(xyxy[3])))
            else:   #没检测到题目
                print(f'Done. ({time.time() - t0:.3f}s)')
                return False

            # Print time (inference + NMS)
            # 打印前向传播+nms时间
            print(f'{s}Done. ({t2 - t1:.3f}s)')

            # Stream results
            # 如果设置展示，则show图片/视频
            if view_img:
                cv2.imshow(str(p), im0)
                cv2.waitKey(1)  # 1 millisecond

            # Save results (image with detections)
            # 设置保存图片/视频
            if save_img:
                if dataset.mode == 'image':
                    cv2.imwrite(save_path, im0)
                else:  # 'video' or 'stream'
                    if vid_path != save_path:  # new video
                        vid_path = save_path
                        if isinstance(vid_writer, cv2.VideoWriter):
                            vid_writer.release()  # release previous video writer
                        if vid_cap:  # video
                            fps = vid_cap.get(cv2.CAP_PROP_FPS)
                            w = int(vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            h = int(vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        else:  # stream
                            fps, w, h = 30, im0.shape[1], im0.shape[0]
                            save_path += '.mp4'
                        vid_writer = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
                    vid_writer.write(im0)

    if save_txt or save_img:
        s = f"\n{len(list(save_dir.glob('labels/*.txt')))} labels saved to {save_dir / 'labels'}" if save_txt else ''
        print(f"Results saved to {save_dir}{s}")

    # 打印总时间
    print(f'Done. ({time.time() - t0:.3f}s)')
    return True

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3090)