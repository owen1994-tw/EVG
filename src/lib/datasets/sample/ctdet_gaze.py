from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import torch.utils.data as data
import numpy as np
import torch
import json
import cv2
import os
from utils.image import flip, color_aug
from utils.image import get_affine_transform, affine_transform
from utils.image import gaussian_radius, draw_umich_gaussian, draw_msra_gaussian
from utils.image import draw_dense_reg
from utils.image import get_paste_kernel, gkern
import math
import matplotlib.pyplot as plt

def kernel_std_cal(gaussian_bbox, img_height, img_width, bias = 0.5 ,weight = 3 ):

    min_img = min(img_height,img_width)
    min_bbox = min(gaussian_bbox[2]-gaussian_bbox[0],gaussian_bbox[3]-gaussian_bbox[1])
    
    # color = (0, 0, 255)  # BGR 格式的顏色，這裡使用綠色
    # thickness = 2  # 矩形框的線條寬度
    # cv2.rectangle(img, (int(gaussian_bbox[0]), int(gaussian_bbox[1])), (int(gaussian_bbox[2]), int(gaussian_bbox[3])), color, thickness)

    
    std = (math.log10(min_img/min_bbox)+bias)*weight
    

    
    # cv2.imshow('Image', img)
    # cv2.waitKey(0)  # 等待使用者按下任意鍵結束視窗
    # cv2.destroyAllWindows()  # 關閉視窗
    
    
    return std



class CTDet_gazeDataset(data.Dataset):
  def _get_border(self, border, size):
    i = 1
    while size - border // i <= border // i:
        i *= 2
    return border // i

  def __getitem__(self, index):
    img_id = self.images[index]
    # print(f"img_id{img_id}")
    file_name = self.coco.loadImgs(ids=[img_id])[0]['file_name']
    img_path = os.path.join(self.img_dir, file_name)
    ann_ids = self.coco.getAnnIds(imgIds=[img_id])
    anns = self.coco.loadAnns(ids=ann_ids)
    num_objs = min(len(anns), self.max_objs)
    # print(num_objs)
  
    img = cv2.imread(img_path)
    raw_img_height, raw_img_width = img.shape[0], img.shape[1] 
    
    

    if np.random.random() <= self.opt.face_crop_ratio :  
      # set face_crop_ratio to process face crop image to be train, with probability to train 
      # with mixing face crop and non-face crop data
      for k in range(num_objs):
        ann = anns[k]
        # faceBbox_list = ann['faceBbox']
        # faceBbox  = faceBbox_list[0]
        # faceBbox = eval(faceBbox)
        # bbox = np.array([faceBbox[0], faceBbox[1], faceBbox[2] , faceBbox[3]],dtype=np.float32)
        bbox = np.array(eval(ann['faceBbox'][0]), dtype=np.float32)
        
        # img_bg = np.zeros_like(img)
        

        img_average_color = cv2.mean(img)[:3]  
        
        # img_bg = np.zeros_like(img)
        img_bg = np.zeros_like(img)
        
        img_bg[:] = img_average_color
        # img_black[int(bbox[1]):int(bbox[3]) , int(bbox[0]):int(bbox[2])] = img[int(bbox[1]):int(bbox[3]) , int(bbox[0]):int(bbox[2])]
        w = (bbox[3] - bbox[1]) * 1.5
        w_c = (bbox[3] + bbox[1]) /2
        h = (bbox[2] - bbox[0]) * 1.5
        h_c = (bbox[2] + bbox[0]) / 2
        bbox[1] = w_c - w/2 
        bbox[3] = w_c + w/2 
        bbox[0] = h_c - h/2 
        bbox[2] = h_c + h/2 
        img_bg[int(bbox[1]):int(bbox[3]) , int(bbox[0]):int(bbox[2])] = img[int(bbox[1]):int(bbox[3]) , int(bbox[0]):int(bbox[2])]
        img = img_bg

    
   
    if self.opt.resize_raw_image:
      img = cv2.resize(img, (self.opt.resize_raw_image_w, self.opt.resize_raw_image_h), interpolation=cv2.INTER_LINEAR)
    
    if self.opt.gray_image:
      img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
      if self.opt.gray_image_with_equalizeHist:
        img = cv2.equalizeHist(img)
      # print("image shape: ",img.shape)
      img = np.repeat(img[..., np.newaxis], 3, -1)
      # print("image shape: ",img.shape)
    
    img_height, img_width = img.shape[0], img.shape[1]
    input_h, input_w = self.opt.input_h, self.opt.input_w
    # print(img_height)
    # print(img_width)
    # print(input_h)
    # print(input_w)

    c = np.array([img.shape[1] / 2., img.shape[0] / 2.], dtype=np.float32)
    if self.opt.keep_res:
      input_h = (img_height | self.opt.pad) + 1
      input_w = (img_width | self.opt.pad) + 1
      s = np.array([input_w, input_h], dtype=np.float32)
    else:
      s = max(img_width, img_height) * 1.0
      input_h, input_w = self.opt.input_h, self.opt.input_w
    # print(self.opt.keep_res)
    # print(self.opt.pad)
    # print(f"input_w, input_h: {input_w}, {input_h}")

   
    
    flipped = False
    if self.split == 'train':
      # pass
      if np.random.random() < self.opt.flip:
        flipped = True
        img = img[:, ::-1, :].copy()
      # flipped = True
      # img = img[:, ::-1, :].copy()
        
    trans_input = get_affine_transform(c, s, 0, [input_w, input_h])
    inp = cv2.warpAffine(img, trans_input, 
                         (input_w, input_h),
                         flags=cv2.INTER_LINEAR)

    inp = (inp.astype(np.float32) / 255.)
    # if self.split == 'train' and not self.opt.no_color_aug:
    #   color_aug(self._data_rng, inp, self._eig_val, self._eig_vec)
    if not self.opt.gray_image:
      inp = (inp - self.mean) / self.std
    inp = inp.transpose(2, 0, 1)

    output_h = input_h // self.opt.down_ratio
    output_w = input_w // self.opt.down_ratio
    
    # for face_hm 
    trans_image_output = get_affine_transform(c, s, 0, [output_w, output_h])
    

    num_classes = self.num_classes
  
    hm = np.zeros((num_classes, output_h, output_w), dtype=np.float32)
    reg = np.zeros((self.max_objs, 2), dtype=np.float32)
    ind = np.zeros((self.max_objs), dtype=np.int64)
    reg_mask = np.zeros((self.max_objs), dtype=np.uint8)
    face_grid = np.zeros((self.max_objs, 2), dtype=np.int64)
    face_hm = np.zeros((num_classes, output_h, output_w), dtype=np.float32)

    draw_gaussian = draw_msra_gaussian if self.opt.mse_loss else \
                    draw_umich_gaussian
                    
      
      
    gt_det = []
    for k in range(num_objs):
      ann = anns[k]
      
      unit_mm,unit_pixel = ann["screenSize"]
      unit_mm = eval(unit_mm)
      raw_sc_width_mm, raw_sc_height_mm = unit_mm  
      
      unit_pixel = eval(unit_pixel)
      raw_sc_width, raw_sc_height = unit_pixel  
      # print("screenSize unit_pixel",f'{sc_height}, {sc_width}')
      # sc = np.ones((1, sc_width, sc_height), dtype=np.float32)
      
      # print("file_name",f'{file_name}')
      # print("unit_mm",f'{sc_width_mm} {sc_height_mm}')
      
      if self.opt.vp_pixel_per_mm > 0 :
        vp_pixel_per_mm = self.opt.vp_pixel_per_mm
      else : 
        vp_pixel_per_mm = raw_sc_width /raw_sc_width_mm
        
      # print("vp_pixel_per_mm = ",vp_pixel_per_mm)
        
      # 5 pixel/mm  norm_screen_plane
      if vp_pixel_per_mm > 0 :
        sc_height = int(raw_sc_height_mm * vp_pixel_per_mm)
        sc_width = int(raw_sc_width_mm * vp_pixel_per_mm)
      else:
        sc_height = raw_sc_height
        sc_width = raw_sc_width
     
      vp_width, vp_height = self.opt.vp_w, self.opt.vp_h
      # vp = np.zeros((1, vp_width, vp_height), dtype=np.float32)
      vp = np.zeros((vp_height, vp_width , 1), dtype=np.float32)
      vp = vp.transpose(1,2,0)
      
      
      
      
      raw_x,raw_y = ann['gazepoint']
      
      # print(self.opt.vp_pixel_per_mm)
      if vp_pixel_per_mm > 0 :
        x = int((raw_x / raw_sc_width) * sc_width)
        y = int((raw_y / raw_sc_height) * sc_height)
      else:
        x = raw_x
        y = raw_y
      # print("raw gazepoint",f'{x} {y}')
      # print("raw sc_size ",f'{raw_sc_width} {raw_sc_height}')
      
      # print("gazepoint",f'{x} {y}')
      # print("sc_size ",f'{sc_width} {sc_height}')
      if flipped:
        x = sc_width - x - 1
      
      sc_gazepoint = np.array([x,y],dtype=np.int64)

      if self.opt.dataset == "gazecapture" :
        _ ,tvecs = ann['monitorPose']
        # in mm 
        tvecs = eval(tvecs)
        x_cameraToScreen_mm, y_cameraToScreen_mm, _ = tvecs 
        
        if self.opt.camera_screen_pos:
          # print("x_cameraToScreen_mm : ",x_cameraToScreen_mm)
          # print("y_cameraToScreen_mm : ",y_cameraToScreen_mm)
          
          camera_screen_x_offset = x_cameraToScreen_mm * vp_pixel_per_mm
          camera_screen_y_offset = y_cameraToScreen_mm * vp_pixel_per_mm
          # print("camera_screen_x_offset : ",camera_screen_x_offset)
          # print("camera_screen_y_offset : ",camera_screen_y_offset)
        else:
          camera_screen_x_offset = 0
          camera_screen_y_offset = 0
          
      elif self.opt.dataset == "himax" :
        
        if self.opt.camera_screen_pos:
          camera_screen_x_offset = 0
          camera_screen_y_offset = sc_height/2 + 78* vp_pixel_per_mm 
          # 78 mm camera to screen
        else:
          camera_screen_x_offset = 0
          camera_screen_y_offset = 0
            
      elif self.opt.dataset == "cross_eve_himax" :

        if self.split == 'train':
          # train eve in pixel   
          if self.opt.camera_screen_pos:
            camera_screen_x_offset = 0
            camera_screen_y_offset = sc_height/2
          else:
            camera_screen_x_offset = 0
            camera_screen_y_offset = 0
        else:
          # val himax in pixel 
          if self.opt.camera_screen_pos:
            camera_screen_x_offset = 0
            camera_screen_y_offset = sc_height/2 + 78* vp_pixel_per_mm 
            # 78 mm camera to screen
          else:
            camera_screen_x_offset = 0
            camera_screen_y_offset = 0
            
      elif self.opt.dataset == "cross_mpii_himax" :

        if self.split == 'train':
          # train mpiifacegaze in pixel   
          if self.opt.camera_screen_pos:
            camera_screen_x_offset = 0
            camera_screen_y_offset = sc_height/2
          else:
            camera_screen_x_offset = 0
            camera_screen_y_offset = 0
        else:
          # val himax in pixel 
          if self.opt.camera_screen_pos:
            camera_screen_x_offset = 0
            camera_screen_y_offset = sc_height/2 + 78* vp_pixel_per_mm 
            # 78 mm camera to screen
          else:
            camera_screen_x_offset = 0
            camera_screen_y_offset = 0
          
      else :
        # mpiifacegaze / eve in pixel
        if self.opt.camera_screen_pos:
          camera_screen_x_offset = 0
          camera_screen_y_offset = sc_height/2
        else:
          camera_screen_x_offset = 0
          camera_screen_y_offset = 0
        # print(f"sc_gazepoint: {sc_gazepoint}")
      # vp_gazepoint = [(vp_width-sc_width)/2+sc_gazepoint[0] ,(vp_height-sc_height)/2+sc_gazepoint[1]+camera_screen_offset]
      vp_gazepoint = np.array([(vp_width/2)+(sc_gazepoint[0]-(sc_width/2))+ camera_screen_x_offset, (vp_height/2)+(sc_gazepoint[1]-(sc_height/2))+camera_screen_y_offset], dtype=np.float32)
      # vp_gazepoint = np.array([(vp_width/2)+(sc_gazepoint[0]-(sc_width/2))+ camera_screen_x_offset, (vp_height/2)+(sc_gazepoint[1]-(sc_height/2))+camera_screen_y_offset], dtype=np.float32)
      # print(f"vp_gazepoint: {vp_gazepoint}")
      # **************
      
      if vp_gazepoint[0] >= vp_width or vp_gazepoint[0] < 0 or vp_gazepoint[1] >= vp_height or vp_gazepoint[1] < 0:
        print("clamp vp_gazepoint before : ",vp_gazepoint)
        print("sc_gazepoint : ",sc_gazepoint)
        vp_gazepoint[0] = max(min(vp_gazepoint[0], vp_width-1), 0)
        vp_gazepoint[1] = max(min(vp_gazepoint[1], vp_height-1), 0)
        print("clamp vp_gazepoint after : ",vp_gazepoint)


      if flipped:
        vp = vp[:, ::-1, :].copy()
          
      vp_c = np.array([ vp_width / 2.0, vp_height/ 2.0], dtype=np.float32)
      if self.opt.keep_res:
        # trans_output_h = (vp_height | self.opt.pad) + 1
        # trans_output_w = (vp_width | self.opt.pad) + 1
        # vp_s = np.array([trans_output_w, trans_output_h], dtype=np.float32)
        trans_output_h = (vp_height | self.opt.pad) + 1
        trans_output_w = (vp_width | self.opt.pad) + 1
        vp_s = np.array([vp_width, vp_height], dtype=np.float32)
      else:
        vp_s = max(vp_width, vp_height) * 1.0
      #  print(f"vp_s: {vp_s}")
      
      # print(f"output_w, output_h: {output_w}, {output_h}")
          
      trans_vp2out = get_affine_transform(vp_c, vp_s, 0, [output_w, output_h])
      # vp_trans_out = cv2.warpAffine(vp, trans_vp2out, 
      #                   (output_w, output_h),
      #                   flags=cv2.INTER_LINEAR)

      # print(f"vp_out: {vp_trans_out.shape[0]},{vp_trans_out.shape[1]}")
      
      
      cls_id = 0
      #   print(vp_gazepoint)
      vp_gazepoint_output = affine_transform(vp_gazepoint, trans_vp2out)
      # print(vp_gazepoint_output)
      h, w = self.opt.vp_heatmap_hw, self.opt.vp_heatmap_hw
      if h > 0 and w > 0:
        gaussian_kernel = 0
        if gaussian_kernel:
          gaussian_bbox = np.array(eval(ann['faceBbox'][0]), dtype=np.float32)
          # scale_x, scale_y = 1,1
          if self.opt.resize_raw_image:
            scale_x = self.opt.resize_raw_image_w / raw_img_width
            scale_y = self.opt.resize_raw_image_h / raw_img_height
            gaussian_bbox[0] = gaussian_bbox[0] * scale_x
            gaussian_bbox[2] = gaussian_bbox[2] * scale_x
            gaussian_bbox[1] = gaussian_bbox[1] * scale_y
            gaussian_bbox[3] = gaussian_bbox[3] * scale_y
          
          if flipped:
            gaussian_bbox[[0, 2]] = img_width - gaussian_bbox[[2, 0]] - 1
        
        
          kernel_std = kernel_std_cal(gaussian_bbox, img_height, img_width, self.opt.vp_gkern_r_bias, self.opt.vp_gkern_r_bias )
          kernel_map = gkern(51, kernel_std)
          ct = np.array([ vp_gazepoint_output[0], vp_gazepoint_output[1]], dtype=np.float32)
          ct_int = ct.astype(np.int32)
          # print(kernel_map.shape)
          # print("h,w", hm.shape[2] , w)
          hm[cls_id] = get_paste_kernel((output_h, output_w), ct_int, kernel_map, (output_h, output_w))
        
        
        else:
          radius = gaussian_radius((math.ceil(h), math.ceil(w)))
          radius = max(0, int(radius))
          radius = self.opt.hm_gauss if self.opt.mse_loss else radius
          ct = np.array([ vp_gazepoint_output[0], vp_gazepoint_output[1]], dtype=np.float32)
          ct_int = ct.astype(np.int32)
          draw_gaussian(hm[cls_id], ct_int, radius)
        
        
        # print("ct_int = ", ct_int)
        

        # hm_gazepoint_idx = np.where(hm[cls_id] == 20)
        # print(f"hm_gazepoint_idx: {hm_gazepoint_idx}")
        
        # avoid exceess the max of ind which accroding to output_h*output_w 
        if ct_int[1] >= output_h :
          ind[k] = (output_h-1) * output_w + ct_int[0]
        else:
          ind[k] = ct_int[1] * output_w + ct_int[0]
        # ind[k] = np.clip(ind[k],0,output_w*output_h)
        reg[k] = ct - ct_int
        reg_mask[k] = 1
        face_grid[k] = 1
        # print('---------------')
        # print("ct",f'{ct}')
        # print("ct_int",f'{ct_int}')
        # print("reg[k]",f'{reg[k]}')
        # print("radius",f'{radius}')

        gt_det.append([ct[0], ct[1], 1, cls_id])
        
        
        
      # faceBbox_list = ann['faceBbox']
      # faceBbox  = faceBbox_list[0]
      # faceBbox = eval(faceBbox)
      # bbox = np.array([faceBbox[0], faceBbox[1], faceBbox[2] , faceBbox[3]],dtype=np.float32)
      
      
      if self.opt.face_hm_head :
        bbox = np.array(eval(ann['faceBbox'][0]), dtype=np.float32)
        
        # scale_x, scale_y = 1,1
        if self.opt.resize_raw_image:
          scale_x = self.opt.resize_raw_image_w / raw_img_width
          scale_y = self.opt.resize_raw_image_h / raw_img_height
          bbox[0] = bbox[0] * scale_x
          bbox[2] = bbox[2] * scale_x
          bbox[1] = bbox[1] * scale_y
          bbox[3] = bbox[3] * scale_y
        
        if flipped:
          bbox[[0, 2]] = img_width - bbox[[2, 0]] - 1
        bbox[:2] = affine_transform(bbox[:2], trans_image_output)
        bbox[2:] = affine_transform(bbox[2:], trans_image_output)
        bbox[[0, 2]] = np.clip(bbox[[0, 2]], 0, output_w - 1)
        bbox[[1, 3]] = np.clip(bbox[[1, 3]], 0, output_h - 1)
      
      
        bbox_h, bbox_w = bbox[3] - bbox[1], bbox[2] - bbox[0]
        if bbox_h > 0 and bbox_w > 0:
          bbox_radius = gaussian_radius((math.ceil(bbox_h), math.ceil(bbox_w)))
          bbox_radius = max(0, int(bbox_radius))
          bbox_radius = self.opt.hm_gauss if self.opt.mse_loss else radius
          bbox_ct = np.array(
            [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2], dtype=np.float32)
          bbox_ct_int = bbox_ct.astype(np.int32)
          draw_gaussian(face_hm[cls_id], bbox_ct_int, bbox_radius)

    # print("vp_trans_out.shape",f'{vp_trans_out.shape}') 
    # print("ct_int",f'{ct_int}') 
    # vp_trans_out[ct_int[1],ct_int[0]] = 1
    # hm  = hm + vp_trans_out
    
    # ret = {'input': inp, 'hm': hm, 'reg_mask': reg_mask, 'ind': ind, 'vp' : vp}
    ret = {'input': inp, 'hm': hm, 'reg_mask': reg_mask, 'ind': ind}
    if self.opt.reg_offset:
      ret.update({'reg': reg})
    if self.opt.face_grid:
      ret.update({'face_grid': face_grid})
    # if self.opt.debug > 0 or not self.split == 'train':
    if self.opt.face_hm_head: 
      ret.update({'face_bbox': bbox})
      ret.update({'face_hm': face_hm})
    
    pog_loss = 1
    if pog_loss:  
      gt_det = np.array(gt_det, dtype=np.float32) if len(gt_det) > 0 else \
               np.zeros((1, 4), dtype=np.float32)
      meta = {'c': c, 's': s,'vp_c': vp_c, 'vp_s': vp_s, 'gt_det': gt_det, 'img_id': img_id,'vp_gazepoint': vp_gazepoint}
      ret['meta'] = meta
    return ret