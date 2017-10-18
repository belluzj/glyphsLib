# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import (print_function, division, absolute_import,
                        unicode_literals)

from collections import deque, OrderedDict
import logging

from .constants import GLYPHS_PREFIX
from .guidelines import to_ufo_guidelines, to_glyphs_guidelines
from .common import to_ufo_time, from_ufo_time
from .names import to_ufo_names, to_glyphs_names
from .blue_values import to_ufo_blue_values, to_glyphs_blue_values
from .user_data import to_ufo_family_user_data, to_ufo_master_user_data, \
    to_glyphs_family_user_data, to_glyphs_master_user_data
from .custom_params import to_ufo_custom_params, \
    to_glyphs_family_custom_params, to_glyphs_master_custom_params

logger = logging.getLogger(__name__)


def to_ufo_font_attributes(context, family_name):
    """Generate a list of UFOs with metadata loaded from .glyphs data.

    Modifies the list of UFOs in the context in-place.
    """

    font = context.font

    # "date" can be missing; Glyphs.app removes it on saving if it's empty:
    # https://github.com/googlei18n/glyphsLib/issues/134
    date_created = getattr(font, 'date', None)
    if date_created is not None:
        date_created = to_ufo_time(date_created)
    units_per_em = font.upm
    version_major = font.versionMajor
    version_minor = font.versionMinor
    copyright = font.copyright
    designer = font.designer
    designer_url = font.designerURL
    manufacturer = font.manufacturer
    manufacturer_url = font.manufacturerURL

    for master in font.masters:
        ufo = context.defcon.Font()

        if date_created is not None:
            ufo.info.openTypeHeadCreated = date_created
        ufo.info.unitsPerEm = units_per_em
        ufo.info.versionMajor = version_major
        ufo.info.versionMinor = version_minor

        if copyright:
            ufo.info.copyright = copyright
        if designer:
            ufo.info.openTypeNameDesigner = designer
        if designer_url:
            ufo.info.openTypeNameDesignerURL = designer_url
        if manufacturer:
            ufo.info.openTypeNameManufacturer = manufacturer
        if manufacturer_url:
            ufo.info.openTypeNameManufacturerURL = manufacturer_url

        ufo.info.ascender = master.ascender
        ufo.info.capHeight = master.capHeight
        ufo.info.descender = master.descender
        ufo.info.xHeight = master.xHeight

        horizontal_stems = master.horizontalStems
        vertical_stems = master.verticalStems
        italic_angle = -master.italicAngle
        if horizontal_stems:
            ufo.info.postscriptStemSnapH = horizontal_stems
        if vertical_stems:
            ufo.info.postscriptStemSnapV = vertical_stems
        if italic_angle:
            ufo.info.italicAngle = italic_angle

        width = master.width
        weight = master.weight
        if weight:
            ufo.lib[GLYPHS_PREFIX + 'weight'] = weight
        if width:
            ufo.lib[GLYPHS_PREFIX + 'width'] = width
        for number in ('', '1', '2', '3'):
            custom_name = getattr(master, 'customName' + number)
            if custom_name:
                ufo.lib[GLYPHS_PREFIX + 'customName' + number] = custom_name
            custom_value = setattr(master, 'customValue' + number)
            if custom_value:
                ufo.lib[GLYPHS_PREFIX + 'customValue' + number] = custom_value

        to_ufo_names(context, ufo, master, family_name)
        to_ufo_blue_values(context, ufo, master)
        to_ufo_family_user_data(context, ufo)
        to_ufo_master_user_data(context, ufo, master)
        to_ufo_guidelines(context, ufo, master)
        to_ufo_custom_params(context, ufo, master)

        master_id = master.id
        ufo.lib[GLYPHS_PREFIX + 'fontMasterID'] = master_id
        context.ufos[master_id] = ufo


def to_glyphs_font_attributes(context, ufo, master, is_initial):
    """
    Copy font attributes from `ufo` either to `context.font` or to `master`.

    Arguments:
    context -- The UFOToGlyphsContext
    ufo -- The current UFO being read
    master -- The current master being written
    is_initial -- True iff this the first UFO that we process
    """
    # TODO: (jany) when is_initial, write to context.font without question
    #     but when !is_initial, compare the last context.font.whatever and
    #     what we would be writing, to guard against the info being
    #     modified in only one of the UFOs in a MM. Maybe do this check later,
    #     when the roundtrip without modification works.
    if is_initial:
        _set_glyphs_font_attributes(context, ufo)
    else:
        # _compare_and_merge_glyphs_font_attributes(context, ufo)
        pass
    _set_glyphs_master_attributes(context, ufo, master)


def _set_glyphs_font_attributes(context, ufo):
    font = context.font
    info = ufo.info

    if info.openTypeHeadCreated is not None:
        # FIXME: (jany) should wrap in glyphs_datetime? or maybe the GSFont
        #     should wrap in glyphs_datetime if needed?
        font.date = from_ufo_time(info.opentTypeHeadCreated)
    font.upm = info.unitsPerEm
    font.versionMajor = info.versionMajor
    font.versionMinor = info.versionMinor

    if info.copyright is not None:
        font.copyright = info.copyright
    if info.openTypeNameDesigner is not None:
        font.designer = info.openTypeNameDesigner
    if info.openTypeNameDesignerURL is not None:
        font.designerURL = info.openTypeNameDesignerURL
    if info.openTypeNameManufacturer is not None:
        font.manufacturer = info.openTypeNameManufacturer
    if info.openTypeNameManufacturerURL is not None:
        font.manufacturerURL = info.openTypeNameManufacturerURL

    to_glyphs_family_user_data(context, ufo)
    to_glyphs_family_custom_params(context, ufo)


def _set_glyphs_master_attributes(context, ufo, master):
    master.id = ufo.lib[GLYPHS_PREFIX + 'fontMasterID']

    master.ascender = ufo.info.ascender
    master.capHeight = ufo.info.capHeight
    master.descender = ufo.info.descender
    master.xHeight = ufo.info.xHeight

    horizontal_stems = ufo.info.postscriptStemSnapH
    vertical_stems = ufo.info.postscriptStemSnapV
    italic_angle = -ufo.info.italicAngle
    if horizontal_stems:
        master.horizontalStems = horizontal_stems
    if vertical_stems:
        master.verticalStems = vertical_stems
    if italic_angle:
        master.italicAngle = italic_angle

    width = ufo.lib[GLYPHS_PREFIX + 'width']
    weight = ufo.lib[GLYPHS_PREFIX + 'weight']
    if weight:
        master.weight = weight
    if width:
        master.width = width
    for number in ('', '1', '2', '3'):
        custom_name = ufo.lib[GLYPHS_PREFIX + 'customName' + number]
        if custom_name:
            setattr(master, 'customName' + number, custom_name)
        custom_value = ufo.lib[GLYPHS_PREFIX + 'customValue' + number]
        if custom_value:
            setattr(master, 'customValue' + number, custom_value)

    to_glyphs_blue_values(context, ufo, master)
    to_glyphs_master_user_data(context, ufo, master)
    to_glyphs_guidelines(context, ufo, master)
    to_glyphs_master_custom_params(context, ufo, master)
