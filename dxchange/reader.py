#!/usr/bin/env python
# -*- coding: utf-8 -*-

# #########################################################################
# Copyright (c) 2015, UChicago Argonne, LLC. All rights reserved.         #
#                                                                         #
# Copyright 2015. UChicago Argonne, LLC. This software was produced       #
# under U.S. Government contract DE-AC02-06CH11357 for Argonne National   #
# Laboratory (ANL), which is operated by UChicago Argonne, LLC for the    #
# U.S. Department of Energy. The U.S. Government has rights to use,       #
# reproduce, and distribute this software.  NEITHER THE GOVERNMENT NOR    #
# UChicago Argonne, LLC MAKES ANY WARRANTY, EXPRESS OR IMPLIED, OR        #
# ASSUMES ANY LIABILITY FOR THE USE OF THIS SOFTWARE.  If software is     #
# modified to produce derivative works, such modified software should     #
# be clearly marked, so as not to confuse it with the version available   #
# from ANL.                                                               #
#                                                                         #
# Additionally, redistribution and use in source and binary forms, with   #
# or without modification, are permitted provided that the following      #
# conditions are met:                                                     #
#                                                                         #
#     * Redistributions of source code must retain the above copyright    #
#       notice, this list of conditions and the following disclaimer.     #
#                                                                         #
#     * Redistributions in binary form must reproduce the above copyright #
#       notice, this list of conditions and the following disclaimer in   #
#       the documentation and/or other materials provided with the        #
#       distribution.                                                     #
#                                                                         #
#     * Neither the name of UChicago Argonne, LLC, Argonne National       #
#       Laboratory, ANL, the U.S. Government, nor the names of its        #
#       contributors may be used to endorse or promote products derived   #
#       from this software without specific prior written permission.     #
#                                                                         #
# THIS SOFTWARE IS PROVIDED BY UChicago Argonne, LLC AND CONTRIBUTORS     #
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT       #
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS       #
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL UChicago     #
# Argonne, LLC OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,        #
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,    #
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;        #
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER        #
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT      #
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN       #
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE         #
# POSSIBILITY OF SUCH DAMAGE.                                             #
# #########################################################################

"""
Module for importing data files.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)


__author__ = "Doga Gursoy, Francesco De Carlo"
__copyright__ = "Copyright (c) 2015-2016, UChicago Argonne, LLC."
__version__ = "0.1.0"
__docformat__ = 'restructuredtext en'
__all__ = ['read_edf',
           'read_hdf5',
           'read_netcdf4',
           'read_npy',
           'read_spe',
           'read_fits',
           'read_tiff',
           'read_tiff_stack',
           'read_xrm',
           'read_xrm_stack',
           'read_hdf5_stack']


import numpy as np
import six
import os
import h5py
import logging
import re
import math
import struct
import dxchange.writer as writer
from dxchange.dtype import empty_shared_array

logger = logging.getLogger(__name__)


def _check_import(modname):
    try:
        return __import__(modname)
    except ImportError:
        logger.warn(modname + ' module not found')
        return None

# Optional dependencies.
spefile = _check_import('spefile')
netCDF4 = _check_import('netCDF4')
EdfFile = _check_import('EdfFile')
# commented out astropy till https://github.com/data-exchange/dxchange/issues/26 is solved
#astropy = _check_import('astropy')
olefile = _check_import('olefile')


# FIXME: raise exception would make more sense, also not sure an extension check
# is very useful, unless we are automatically mapping an extension to a
# function.
def _check_read(fname):
    known_extensions = ['.edf', '.tiff', '.tif', '.h5', '.hdf', '.npy', '.xrm']
    if not isinstance(fname, six.string_types):
        logger.error('File name must be a string')
    else:
        if writer.get_extension(fname) not in known_extensions:
            logger.error('Unknown file extension')
    return os.path.abspath(fname)


def read_tiff(fname, slc=None):
    """
    Read data from tiff file.

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.
    slc : sequence of tuples, optional
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.

    Returns
    -------
    ndarray
        Output 2D image.
    """
    fname = _check_read(fname)
    try:
        import tifffile
        arr = tifffile.imread(fname, memmap=True)
    except IOError:
        logger.error('No such file or directory: %s', fname)
        return False
    arr = _slice_array(arr, slc)
    _log_imported_data(fname, arr)
    return arr


def read_tiff_stack(fname, ind, digit, slc=None):
    """
    Read data from stack of tiff files in a folder.

    Parameters
    ----------
    fname : str
        One of the file names in the tiff stack.
    ind : list of int
        Indices of the files to read.
    digit : int
        Number of digits used in indexing stacked files.
    slc : sequence of tuples, optional
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.

    Returns
    -------
    ndarray
        Output 3D image.
    """
    fname = _check_read(fname)
    list_fname = _list_file_stack(fname, ind, digit)

    arr = _init_arr_from_stack(list_fname[0], len(ind), slc)
    for m, fname in enumerate(list_fname):
        arr[m] = read_tiff(fname, slc)
    _log_imported_data(fname, arr)
    return arr

def read_xrm(fname, slc=None):
    """
    Read data from xrm file.

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.
    slc : sequence of tuples, optional
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.

    Returns
    -------
    ndarray
        Output 2D image.
    """
    fname = _check_read(fname)
    try:
        import olefile
        ole = olefile.OleFileIO(fname)
    except IOError:
        print('No such file or directory: %s', fname)
        return False

    n_cols = _read_label(ole, 'ImageInfo/ImageWidth', '<I')
    n_rows = _read_label(ole, 'ImageInfo/ImageHeight', '<I')
    d_type = _read_label(ole, 'ImageInfo/DataType', '<1I')

    # 10 float; 5 uint16 (unsigned 16-bit (2-byte) integers)
    if d_type == 10:
        struct_fmt = "<{}f".format(n_cols*n_rows)
    elif d_type == 5:                   
        struct_fmt = "<{}h".format(n_cols*n_rows)
    
    img = _read_data(ole, "ImageData1/Image1", struct_fmt)

    arr = np.zeros((n_cols, n_rows))    
    arr[:,:] = np.reshape(img, (n_cols, n_rows), order='F')
    arr = np.swapaxes(arr,0,1)

    arr = _slice_array(arr, slc)  
    _log_imported_data(fname, arr)
    return arr

def read_xrm_stack(fname, ind, digit, slc=None):
    """
    Read data from stack of xrm files in a folder.

    Parameters
    ----------
    fname : str
        One of the file names in the tiff stack.
    ind : list of int
        Indices of the files to read.
    digit : int
        Number of digits used in indexing stacked files.
    slc : sequence of tuples, optional
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.

    Returns
    -------
    ndarray
        Output 3D image.
    """
    fname = _check_read(fname)
    list_fname = _list_file_stack(fname, ind, digit)

    arr = _init_ole_arr_from_stack(list_fname[0], len(ind), slc)
    for m, fname in enumerate(list_fname):
        arr[m] = read_xrm(fname, slc)
    _log_imported_data(fname, arr)
    return arr


def _log_imported_data(fname, arr):
    logger.debug('Data shape & type: %s %s', arr.shape, arr.dtype)
    logger.info('Data succesfully imported: %s', fname)


def _init_arr_from_stack(fname, nfile, slc):
    """
    Initialize numpy array from files in a folder.
    """
    _arr = read_tiff(fname, slc)
    size = (nfile, _arr.shape[0], _arr.shape[1])
    logger.debug('Data initialized with size: %s', size)
    return np.zeros(size, dtype=_arr.dtype)

def _init_ole_arr_from_stack(fname, nfile, slc):
    """
    Initialize numpy array from files in a folder.
    """
    _arr = read_xrm(fname, slc)
    size = (nfile, _arr.shape[0], _arr.shape[1])
    logger.debug('Data initialized with size: %s', size)
    return np.zeros(size, dtype=_arr.dtype)


def read_edf(fname, slc=None):
    """
    Read data from edf file.

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.
    slc : sequence of tuples, optional
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.

    Returns
    -------
    ndarray
        Data.
    """
    try:
        fname = _check_read(fname)
        f = EdfFile.EdfFile(fname, access='r')
        d = f.GetStaticHeader(0)
        arr = np.empty((f.NumImages, int(d['Dim_2']), int(d['Dim_1'])))
        for (i, ar) in enumerate(arr):
            arr[i::] = f.GetData(i)
        arr = _slice_array(arr, slc)
    except KeyError:
        logger.error('Unrecognized EDF data format')
        arr = None
    _log_imported_data(fname, arr)
    return arr


def read_hdf5(fname, dataset, slc=None, dtype=None, shared=True):
    """
    Read data from hdf5 file from a specific group.

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.
    dataset : str
        Path to the dataset inside hdf5 file where data is located.
    slc : sequence of tuples, optional
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.
    dtype : numpy datatype (optional)
        Convert data to this datatype on read if specified.
    shared : bool (optional)
        If True, read data into shared memory location.  Defaults to True.

    Returns
    -------
    ndarray
        Data.
    """
    try:
        fname = _check_read(fname)
        with h5py.File(fname, "r") as f:
            try:
                data = f[dataset]
            except KeyError:
                # NOTE: I think it would be better to raise an exception here.
                logger.error('Unrecognized hdf5 dataset: "%s"' %
                             (str(dataset)))
                return None
            shape = _shape_after_slice(data.shape, slc)
            if dtype is None:
                dtype = data.dtype
            if shared:
                arr = empty_shared_array(shape, dtype)
            else:
                arr = np.empty(shape, dtype)
            data.read_direct(arr, _fix_slice(slc))
    except KeyError:
        arr = None
    _log_imported_data(fname, arr)
    return arr


def read_netcdf4(fname, group, slc=None):
    """
    Read data from netcdf4 file from a specific group.

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.
    group : str
        Variable name where data is stored.
    slc : sequence of tuples, optional
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.

    Returns
    -------
    ndarray
        Data.
    """
    fname = _check_read(fname)
    f = netCDF4.Dataset(fname, 'r')
    try:
        arr = f.variables[group]
    except KeyError:
        f.close()
        logger.error('Unrecognized netcdf4 group')
        return None
    arr = _slice_array(arr, slc)
    f.close()
    _log_imported_data(fname, arr)
    return arr


def read_npy(fname, slc=None):
    """
    Read binary data from a ``.npy`` file.

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.
    slc : sequence of tuples, optional
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.

    Returns
    -------
    ndarray
        Data.
    """
    fname = _check_read(fname)
    arr = np.load(fname)
    arr = _slice_array(arr, slc)
    _log_imported_data(fname, arr)
    return arr


def read_spe(fname, slc=None):
    """
    Read data from spe file.

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.
    slc : sequence of tuples, optional
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.

    Returns
    -------
    ndarray
        Data.
    """
    fname = _check_read(fname)
    f = spefile.PrincetonSPEFile(fname)
    arr = f.getData()
    arr = _slice_array(arr, slc)
    _log_imported_data(fname, arr)
    return arr


def _fix_slice(slc):
    """
    Fix up a slc object to be tuple of slices.
    slc = None is treated as no slc
    slc is container and each element is converted into a slice object
    None is treated as slice(None)

    Parameters
    ----------
    slc : None or sequence of tuples
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.  
    """
    if slc is None:
        return None  # need arr shape to create slice
    fixed_slc = list()
    for s in slc:
        if not isinstance(s, slice):
            # create slice object
            if s is None or isinstance(s, int):
                # slice(None) is equivalent to np.s_[:]
                # numpy will return an int when only an int is passed to
                # np.s_[]
                s = slice(s)
            else:
                s = slice(*s)
        fixed_slc.append(s)
    return tuple(fixed_slc)


def read_fits(fname, fixdtype=True):
    """
    Read data from fits file.

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.

    Returns
    -------
    ndarray
        Data.
    """
    # NOTE:
    # at astropy 1.0.5, it is necessary to fix the dtype
    # but at 1.1.1, it seems unnecessary
    def _getDataType(path):
        bitpix = _readBITPIX(path)
        if bitpix > 0:
            dtype = 'uint%s' % bitpix
        elif bitpix <= -32:
            dtype = 'float%s' % -bitpix
        else:
            dtype = 'int%s' % -bitpix
        return dtype

    def _readBITPIX(path):
        # astropy fits reader has a problem
        # have to read BITPIX from the fits file directly
        stream = open(path, 'rb')
        while True:
            line = stream.read(80).decode("utf-8")
            if line.startswith('BITPIX'):
                value = line.split('/')[0].split('=')[1].strip()
                value = int(value)
                break
            continue
        stream.close()
        return value

    from astropy.io import fits
    f = fits.open(fname)
    arr = f[0].data
    f.close()
    if fixdtype:
        dtype = _getDataType(fname)
        if dtype:
            arr = np.array(arr, dtype=dtype)
    _log_imported_data(fname, arr)
    return arr


def _slice_array(arr, slc):
    """
    Perform slicing on ndarray.

    Parameters
    ----------
    arr : ndarray
        Input array to be sliced.
    slc : sequence of tuples
        Range of values for slicing data in each axis.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix.

    Returns
    -------
    ndarray
        Sliced array.
    """
    if slc is None:
        logger.debug('No slicing applied to image')
        return arr[:]
    axis_slice = _fix_slice(slc)
    logger.debug('Data sliced according to: %s', axis_slice)
    return arr[axis_slice]


def _shape_after_slice(shape, slc):
    """
    Return the calculated shape of an array after it has been sliced.  
    Only handles basic slicing (not advanced slicing).

    Parameters
    ----------
    shape : tuple of ints
        Tuple of ints defining the ndarray shape
    slc : tuple of slices
        Object representing a slice on the array.  Should be one slice per
        dimension in shape.

    """
    if slc is None:
        return shape
    new_shape = list(shape)
    slc = _fix_slice(slc)
    for m, s in enumerate(slc):
        # indicies will perform wrapping and such for the shape
        start, stop, step = s.indices(shape[m])
        new_shape[m] = int(math.ceil((stop - start) / float(step)))
        if new_shape[m] < 0:
            new_shape[m] = 0
    return tuple(new_shape)


def _list_file_stack(fname, ind, digit):
    """
    Return a stack of file names in a folder as a list.

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.
    ind : list of int
        Indices of the files to read.
    digit : int
        Number of digits in indexing stacked files.
    """

    body = writer.get_body(fname, digit)
    ext = writer.get_extension(fname)
    list_fname = []
    for m in ind:
        list_fname.append(str(body + '{0:0={1}d}'.format(m, digit) + ext))
    return list_fname

def find_dataset_group(fname):
    """
    Finds the group name containing the stack of projections datasets within
    an ALS BL8.3.2 hdf5 file  containing a stack of images

    Parameters
    ----------
    fname : str
        String defining the path of file or file name.
    
    Returns
    -------
    h5py.Group
    """
    h5object = h5py.File(fname, 'r')
    return _find_dataset_group(h5object)


def _find_dataset_group(h5object):
    """
    Finds the group name containing the stack of projections datasets within
    an ALS BL8.3.2 hdf5 file  containing a stack of images
    """
    
    # Only one root key means only one dataset in BL8.3.2 current format    
    keys = list(h5object.keys())
    if len(keys) == 1:
        if isinstance(h5object[keys[0]], h5py.Group):
            group_keys = list(h5object[keys[0]].keys())
            if isinstance(h5object[keys[0]][group_keys[0]], h5py.Dataset):
                return h5object[keys[0]]
            else:
                return _find_dataset_group(h5object[keys[0]])
        else:
            raise Exception('HDF5 Group with dataset stack not found')
    else:
        raise Exception('HDF5 Group with dataset stack not found')


def _count_proj(group, dname, nproj, digit=4, inter_bright=None):
    """
    Count the number of projections that have a specified name structure.
    Used to count the number of brights or darks in ALS BL8.3.2 hdf5 files when
    number is not present in metadata.
    """

    body = os.path.splitext(dname)[0]
    body = ''.join(body[:-digit])

    regex = re.compile('.*(' + body + ').*')
    count = len(list(filter(regex.match, list(group.keys()))))

    if inter_bright > 0:
        count = count / (nproj / inter_bright + 2)
    elif inter_bright == 0:
        count = count / 2

    return int(count)


def _map_loc(ind, loc):
    """
    Does a linear mapping of the indices where brights where taken within the
    full tomography to new indices of only those porjections which where read
    The returned list of indices is used in normalize_nn function.
    """

    loc = np.array(loc)
    low, upp = ind[0], ind[-1]
    buff = (loc[-1] - loc[0]) / len(loc)
    min_loc = low - buff
    max_loc = upp + buff
    loc = np.intersect1d(loc[loc > min_loc], loc[loc < max_loc])
    new_upp = len(ind)
    loc = (new_upp * (loc - low)) // (upp - low)
    if loc[0] < 0:
        loc[0] = 0

    return np.ndarray.tolist(loc)


def _read_label(ole, label, struct_fmt):
    """
    Reads the integer value associated with label in an ole file
    """
    
    if ole.exists(label):   
        stream = ole.openstream(label)
        data = stream.read()
        nev = struct.unpack(struct_fmt, data)
        value = np.int(nev[0])
    
    return value

def _read_data(ole, label, struct_fmt):
    """
    Reads the array associated with label in an ole file
    """

    if ole.exists(label):   
        stream = ole.openstream(label)
        data = stream.read()
        arr = struct.unpack(struct_fmt, data)
    
    return arr
    
    
def read_hdf5_stack(h5group, dname, ind, digit=4, slc=None, out_ind=None):
    """
    Read data from stacked datasets in a hdf5 file

    Parameters
    ----------

    fname : str
        One of the dataset names in the dataset stack

    ind : list of int
        Indices of the datasets to be read

    digit : int
        Number of digits indexing the stacked datasets

    slc : {sequence, int}
        Range of values for slicing data.
        ((start_1, end_1, step_1), ... , (start_N, end_N, step_N))
        defines slicing parameters for each axis of the data matrix

    out_ind : list of int, optional
        Outer level indices for files with two levels of indexing.
        i.e. [name_000_000.tif, name_000_001.tif, ..., name_000_lmn.tif,
        name_001_lmn.tif, ..., ..., name_fgh_lmn.tif]
    """

    list_fname = _list_file_stack(dname, ind, digit)

    if out_ind is not None:
        list_fname_ = []
        for name in list_fname:
            fname = (writer.get_body(name).split('/')[-1] + '_' + digit * '0' +
                     writer.get_extension(name))
            list_fname_.extend(_list_file_stack(fname, out_ind, digit))
        list_fname = list_fname_

    for m, image in enumerate(list_fname):
        _arr = h5group[image]
        _arr = _slice_array(_arr, slc)
        if m == 0:
            dx, dy, dz = _arr.shape
            dx = len(list_fname)
            arr = np.empty((dx, dy, dz), dtype=_arr.dtype)
        arr[m] = _arr

    return arr
