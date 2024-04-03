# Copyright (C) 2019 Chintalagiri Shashank
#
# This file is part of Tendril.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Media Content Configuration Options
====================================
"""


from tendril.utils.config import ConfigOption
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)

depends = ['tendril.config.core']

config_elements_imageset = [
    ConfigOption(
        'IMAGESET_IMAGE_EXTENSIONS',
        "['.jpg', '.png']",           # WebP, SVG, Tiff don't play well with MediaInfo
        "List of recognized extensions for image files for imagesets."
    ),
    ConfigOption(
        'IMAGESET_DOCUMENT_EXTENSIONS',
        "['.pdf']",
        "List of recognized extensions for document files for imagesets."
    ),
    ConfigOption(
        'IMAGESET_EXTRA_EXTENSIONS',
        "[]",
        "List of extra extensions to recognize as imageset files. Note "
        "that this is only provided for highly specialized cases and "
        "for development-time use. Extensions listed here will "
        "probably break other code in unpredictable ways if used."
    ),
    ConfigOption(
        'IMAGESET_EXTENSIONS',
        "IMAGESET_IMAGE_EXTENSIONS + IMAGESET_DOCUMENT_EXTENSIONS + IMAGESET_EXTRA_EXTENSIONS",
        "List of recognized extensions for imageset files"
    ),
    ConfigOption(
        'IMAGESET_UPLOAD_FILESTORE_BUCKET',
        '"incoming"',
        "The filestore bucket in which to write uploaded imageset files. Note that filestore "
        "will not have this bucket by default. You must create it or choose one that exists."
    ),
    ConfigOption(
        'IMAGESET_PUBLISHING_FILESTORE_BUCKET',
        '"cdn"',
        "The filestore bucket in which published imageset files are to be written. Note that "
        "filestore will not have this bucket by default. You must create it or choose one "
        "that exists."
    )
]


def load(manager):
    logger.debug("Loading {0}".format(__name__))
    manager.load_elements(config_elements_imageset,
                          doc="ImageSet Content Configuration")
