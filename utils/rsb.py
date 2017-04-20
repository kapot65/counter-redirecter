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

from signal_utils.extract_utils import apply_zsupression
        
def rsb_to_df(ext_meta: dict, rsb_file, 
              threshold: int=500, area_l: int=50, 
              area_r: int=100) -> (dict, bytearray, int):
    """
      Добавление данных, набранных платой Руднева-Шиляева с основным файлом
      с точками.
      
      @meta - метаданные сообщения с точками
      @rsb_file - файл с платы Руднева-Шиляева
      @threshold - порог амплитуды события (параметр zero-suppression)
      @area_l - область около события, которая будет сохранена (параметр 
      zero-suppression)
      @area_r - область около события, которая будет сохранена (параметр 
      zero-suppression)
      @return - (meta, data, data_type)
      
    """
    
    sec_coef = 10e+9
    
    rsb_ds = dfparser.RshPackage(rsb_file)
    
    meta = {}
    meta["external_meta"] = ext_meta
    meta["params"] = rsb_ds.params
    meta["process_params"] = {  
            "threshold": threshold, 
            "area_l": area_l, 
            "area_r": area_r
        }
        
    begin_time = parse(rsb_ds.params["start_time"]).timestamp()*sec_coef
    end_time = parse(rsb_ds.params["end_time"]).timestamp()*sec_coef
    bin_time = (rsb_ds.params["sample_freq"]**-1)*sec_coef
    b_size = rsb_ds.params["b_size"]
    
    
    if rsb_ds.params["events_num"] == -1:
        meta["recalc_events_num"] = True
        rsb_ds.params["events_num"] = np.iinfo(int).max
        for i in range(np.iinfo(int).max):
            try:
                rsb_ds.get_event(i)
            except Exception as e:
                rsb_ds.params["events_num"] = i
                break
    
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
            meta["correcting_time"] = "linear"
   
    point = rsb_event_pb2.Point()
    channels = [point.channels.add(num=ch) for ch in range(ch_num)] 
    for i in range(events_num):
        event_data = rsb_ds.get_event(i)
        
        if use_time_corr:
            time = times[i]
        else:
            time = event_data["ns_since_epoch"] 
          
        for ch in range(ch_num):
            block = channels[ch].blocks.add(time=int(time))
            
            ch_data = event_data["data"][ch::ch_num]
            for frame in apply_zsupression(ch_data, threshold, area_l, area_r):
                frame = np.clip(frame, 0, ch_data.shape[0] - 1)
                event = block.events.add()
                event.time = int(frame[0]*bin_time)
                event.data = ch_data[frame[0]:frame[1]].astype(np.int16)\
                             .tobytes()
    
    meta["bin_offset"] = 0
    meta["bin_size"] = point.ByteSize()
    data = point.SerializeToString()
    
    return meta, data
