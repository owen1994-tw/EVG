from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from .sample.ddd import DddDataset
from .sample.exdet import EXDetDataset
from .sample.ctdet import CTDetDataset
from .sample.ctdet_gaze import CTDet_gazeDataset
from .sample.multi_pose import MultiPoseDataset

from .dataset.coco import COCO
from .dataset.mpiifacegaze import MpiiFaceGaze
from .dataset.gazecapture import GazeCapture
from .dataset.eve import EVE
from .dataset.pascal import PascalVOC
from .dataset.kitti import KITTI
from .dataset.coco_hp import COCOHP


dataset_factory = {
  'coco': COCO,
  'mpiifacegaze': MpiiFaceGaze,
  'gazecapture': GazeCapture,
  'eve': EVE,
  'pascal': PascalVOC,
  'kitti': KITTI,
  'coco_hp': COCOHP
}

_sample_factory = {
  'exdet': EXDetDataset,
  'ctdet': CTDetDataset,
  'ctdet_gaze': CTDet_gazeDataset,
  'ddd': DddDataset,
  'multi_pose': MultiPoseDataset
}


def get_dataset(dataset, task):
  class Dataset(dataset_factory[dataset], _sample_factory[task]):
    pass
  return Dataset
  
