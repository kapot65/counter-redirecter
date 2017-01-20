#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jan 17 01:56:18 2017

@author: chernov
"""

import dfparser
import numpy as np

def zero_suppression(filepath, threshold=500, area_l=50, area_r=100):
    """
      Обрезание шумов в файле данных платы Лан10-12PCI
      
      Функция расчитана на файлы данных с максимальным размером кадра
      (непрерывное считывание с платы). Области без событий будут заменены
      нулями. Результат будет записан в исходный файл
      
      @filepath - путь к файлу данных
      @threshold - порог амплитуды события
      @area_l - область около события, которая будет сохранена
      @area_r - область около события, которая будет сохранена
      
      @todo проверить на двух каналах
      
    """
    
    dataset = dfparser.RshPackage(filepath)
    
    ch_num = dataset.params["ch_num"]
    
    for i in range(dataset.params["events_num"]):
        
        data = dataset.get_event(i)["data"]
        
        for ch in range(ch_num):
            ch1 = data[ch::ch_num]
            
            mask = np.full(ch1.shape, True, np.bool)
            
            peaks = np.where(ch1 > threshold)[0]
            dists = peaks[1:] - peaks[:-1]
            gaps = np.append(np.array([0]), np.where(dists > area_r)[0] + 1)
            
            for gap in range(0, len(gaps) - 1):
               mask[peaks[gaps[gap]] - area_l: 
                    peaks[gaps[gap + 1] - 1] + area_r] = False 
                
            ch1[mask] = 0
        
        dataset.update_event_data(i, data)
        