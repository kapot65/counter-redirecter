#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jan 17 01:56:18 2017

@author: chernov
"""

import sys
from os import path
from dateutil.parser import parse

import dfparser
import numpy as np

cur_dir = path.dirname(path.realpath(__file__))
if not cur_dir in sys.path: sys.path.append(cur_dir)
del cur_dir

import rsb_event_pb2


def apply_zsupression(data: np.ndarray, threshold: int=500, 
                          area_l: int=50, area_r: int=100) -> tuple:
    """
      Обрезание шумов в файле данных платы Лан10-12PCI
      
      Функция расчитана на файлы данных с максимальным размером кадра
      (непрерывное считывание с платы).
      
      @data - данные кадра (отдельный канал)
      @threshold - порог амплитуды события
      @area_l - область около события, которая будет сохранена
      @area_r - область около события, которая будет сохранена
      
      @return список границ события
      
    """
    peaks = np.where(data > threshold)[0]
    dists = peaks[1:] - peaks[:-1]
    gaps = np.append(np.array([0]), np.where(dists > area_r)[0] + 1)
    
    events = ((peaks[gaps[gap]] - area_l, peaks[gaps[gap + 1] - 1] + area_r) 
              for gap in range(0, len(gaps) - 1))
    
    return events

        
def combine_with_rsb(meta: dict, data: bytearray, data_type: int, rsb_file, 
                     threshold: int=500, area_l: int=50, 
                     area_r: int=100) -> (dict, bytearray, int):
    """
      Добавление данных, набранных платой Руднева-Шиляева с основным файлом
      с точками.
      
      @meta - метаданные сообщения с точками
      @data - бинарные данные сообщения с точками
      @data_type - тип бинарных данных
      @rsb_file - файл с платы Руднева-Шиляева
      @threshold - порог амплитуды события (параметр zero-suppression)
      @area_l - область около события, которая будет сохранена (параметр 
      zero-suppression)
      @area_r - область около события, которая будет сохранена (параметр 
      zero-suppression)
      @return - (meta, data, data_type)
      
    """
    
    sec_coef = 10**9
    
    rsb_ds = dfparser.RshPackage(rsb_file)
    
    if not("external_meta" in meta and meta["external_meta"]):
        meta["external_meta"] = {}
    
    meta["external_meta"]["lan10"] = {
        "params": rsb_ds.params,
        "process_params": { 
            "threshold": threshold,
            "area_l": area_l, 
            "area_r": area_r
        },
        "bin_offset": len(data)
    }
        
    begin_time = parse(rsb_ds.params["start_time"]).timestamp()*sec_coef
    end_time = parse(rsb_ds.params["end_time"]).timestamp()*sec_coef
    bin_time = (rsb_ds.params["sample_freq"]**-1)*sec_coef
    b_size = rsb_ds.params["b_size"]
    events_num = rsb_ds.params["events_num"]
    ch_num = rsb_ds.params["channel_number"]
    
    use_time_corr = False
    if events_num > 0:
        ev = rsb_ds.get_event(0)
        if not "ns_since_epoch" in ev:
            use_time_corr = True 
            times = list(np.linspace(begin_time, end_time - 
                                     int(bin_time*b_size), 
                                     events_num))
            meta["external_meta"]["correcting_time"] = "linear"
   
    point = rsb_event_pb2.Point()
    channels = [point.channels.add(num=ch) for ch in range(ch_num)] 
    for i in range(events_num):
        event_data = rsb_ds.get_event(i)
        
        if use_time_corr:
            time = times[i]
        else:
            time = event_data["ns_since_epoch"] 
            print(time)
          
        for ch in range(ch_num):
            block = channels[ch].blocks.add(time=int(time))
            
            ch_data = event_data["data"][ch::ch_num]
            for frame in apply_zsupression(ch_data, threshold, area_l, area_r):
                event = block.events.add()
                event.time = int(frame[0]*bin_time)
                event.data = ch_data[frame[0]:frame[1]].astype(np.int16)\
                             .tobytes()
    
    meta["external_meta"]["lan10"]["bin_size"] = point.ByteSize()
    data += point.SerializeToString()
    
    return meta, data, data_type

        