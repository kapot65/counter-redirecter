#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar 23 11:09:25 2017

@author: chernov
"""

import sys
from os import path
from datetime import datetime

import numpy as np

main_dir = path.abspath(path.join(path.dirname(__file__), '..'))
if not main_dir in sys.path: sys.path.append(main_dir)
del main_dir

from dfparser import Point

if __name__=='__main__':
    
    print('testing protobuf3 memory effectivness')
    n_channels = 1
    n_blocks = 10
    n_samples = 100000
    
    def test_writing(times,
                     amps=None, 
                     data=None,
                     data_size=4,
                     n_channels=n_channels, 
                     n_blocks=n_blocks):
        global point
        if not amps is None: 
            assert len(times) == len(amps)
        if not data is None:
            assert len(times) == len(data)
        
        point = Point()
        for i in range(n_channels):  
            ch = point.channels.add(num=i)
            for j in range(n_blocks):
                block = ch.blocks.add()
                block.time = int(datetime.now().timestamp()*10**9)
                
                
                if data is None:
                    for k, time in enumerate(times):
                        block.peaks.times.append(int(time))
                        if (not amps is None):
                            block.peaks.amplitudes.append(int(amps[k]))
                else:
                    for k, time in enumerate(times):
                        event = block.events.add()
                        event.time = int(time)
                        if not data is None and len(data) > k:
                            event.data = data[k].astype(np.int16).tobytes()
                    
        
        point_size = point.ByteSize()
        best_size = n_channels*n_blocks*len(times)*(data_size + 4)
        print('real size: %s, best size: %s (%s overhead)'%
              (point_size, best_size, point_size/best_size - 1.0))
        
    print('test #1: point with time only')
    test_writing(np.random.randint(0, 2**31, n_samples), data_size=0)
    
    
    print('test #2: point with amp events only, amp < 16 bit')
    test_writing(np.random.randint(0, 2**31, n_samples),
                 amps=np.random.randint(0, 2**15, n_samples, np.uint16), 
                 data_size=2)
    
    print('test #3: point with amp events only, amp > 16 bit')
    test_writing(np.random.randint(0, 2**31, n_samples),
                 amps=np.random.randint(0, 2**31, n_samples), data_size=4)
    
    print('test #4: point with data only')
    test_writing(np.random.randint(0, 2**31, n_samples),
                 data=np.random.randint(0, 2**31, (n_samples, 128)), 
                 data_size=128*2)
    