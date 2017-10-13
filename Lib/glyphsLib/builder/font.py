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

import re
from collections import deque, OrderedDict
import logging

from .constants import PUBLIC_PREFIX, GLYPHS_PREFIX, CODEPAGE_RANGES, \
                       UFO2FT_FILTERS_KEY
from glyphsLib.util import clear_data, cast_to_number_or_bool, bin_to_int_list
from .guidelines import to_ufo_guidelines
from .common import to_ufo_time
from .filters import parse_glyphs_filter
from .names import build_style_name, build_stylemap_names
from .blue_values import set_blue_values

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
    user_data = font.userData
    copyright = font.copyright
    designer = font.designer
    designer_url = font.designerURL
    manufacturer = font.manufacturer
    manufacturer_url = font.manufacturerURL

    misc = ['DisplayStrings', 'disablesAutomaticAlignment', 'disablesNiceNames']
    custom_params = parse_custom_params(font, misc)

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
            is_italic = True
        else:
            is_italic = False

        width = master.width
        weight = master.weight
        custom = master.customName
        if weight:
            ufo.lib[GLYPHS_PREFIX + 'weight'] = weight
        if width:
            ufo.lib[GLYPHS_PREFIX + 'width'] = width
        if custom:
            ufo.lib[GLYPHS_PREFIX + 'custom'] = custom

        styleName = build_style_name(
            width if width != 'Regular' else '',
            weight,
            custom,
            is_italic
        )
        styleMapFamilyName, styleMapStyleName = build_stylemap_names(
            family_name=family_name,
            style_name=styleName,
            is_bold=(styleName == 'Bold'),
            is_italic=is_italic
        )
        ufo.info.familyName = family_name
        ufo.info.styleName = styleName
        ufo.info.styleMapFamilyName = styleMapFamilyName
        ufo.info.styleMapStyleName = styleMapStyleName

        set_blue_values(ufo, master.alignmentZones)
        set_family_user_data(ufo, user_data)
        set_master_user_data(ufo, master.userData)
        to_ufo_guidelines(context, ufo, master)

        set_custom_params(ufo, parsed=custom_params)
        # the misc attributes double as deprecated info attributes!
        # they are Glyphs-related, not OpenType-related, and don't go in info
        misc = ('customValue', 'weightValue', 'widthValue')
        set_custom_params(ufo, data=master, misc_keys=misc, non_info=misc)

        set_default_params(ufo)

        master_id = master.id
        ufo.lib[GLYPHS_PREFIX + 'fontMasterID'] = master_id
        context.ufos[master_id] = ufo


def set_custom_params(ufo, parsed=None, data=None, misc_keys=(), non_info=()):
    """Set Glyphs custom parameters in UFO info or lib, where appropriate.

    Custom parameter data can be pre-parsed out of Glyphs data and provided via
    the `parsed` argument, otherwise `data` should be provided and will be
    parsed. The `parsed` option is provided so that custom params can be popped
    from Glyphs data once and used several times; in general this is used for
    debugging purposes (to detect unused Glyphs data).

    The `non_info` argument can be used to specify potential UFO info attributes
    which should not be put in UFO info.
    """

    if parsed is None:
        parsed = parse_custom_params(data or {}, misc_keys)
    else:
        assert data is None, "Shouldn't provide parsed data and data to parse."

    fsSelection_flags = {'Use Typo Metrics', 'Has WWS Names'}
    for name, value in parsed:
        name = normalize_custom_param_name(name)

        if name in fsSelection_flags:
            if value:
                if ufo.info.openTypeOS2Selection is None:
                    ufo.info.openTypeOS2Selection = []
                if name == 'Use Typo Metrics':
                    ufo.info.openTypeOS2Selection.append(7)
                elif name == 'Has WWS Names':
                    ufo.info.openTypeOS2Selection.append(8)
            continue

        # deal with any Glyphs naming quirks here
        if name == 'disablesNiceNames':
            name = 'useNiceNames'
            value = int(not value)

        # convert code page numbers to OS/2 ulCodePageRange bits
        if name == 'codePageRanges':
            value = [CODEPAGE_RANGES[v] for v in value]

        # convert Glyphs' GASP Table to UFO openTypeGaspRangeRecords
        if name == 'GASP Table':
            name = 'openTypeGaspRangeRecords'
            # XXX maybe the parser should cast the gasp values to int?
            value = {int(k): int(v) for k, v in value.items()}
            gasp_records = []
            # gasp range records must be sorted in ascending rangeMaxPPEM
            for max_ppem, gasp_behavior in sorted(value.items()):
                gasp_records.append({
                    'rangeMaxPPEM': max_ppem,
                    'rangeGaspBehavior': bin_to_int_list(gasp_behavior)})
            value = gasp_records

        opentype_attr_prefix_pairs = (
            ('hhea', 'Hhea'), ('description', 'NameDescription'),
            ('license', 'NameLicense'),
            ('licenseURL', 'NameLicenseURL'),
            ('preferredFamilyName', 'NamePreferredFamilyName'),
            ('preferredSubfamilyName', 'NamePreferredSubfamilyName'),
            ('compatibleFullName', 'NameCompatibleFullName'),
            ('sampleText', 'NameSampleText'),
            ('WWSFamilyName', 'NameWWSFamilyName'),
            ('WWSSubfamilyName', 'NameWWSSubfamilyName'),
            ('panose', 'OS2Panose'),
            ('typo', 'OS2Typo'), ('unicodeRanges', 'OS2UnicodeRanges'),
            ('codePageRanges', 'OS2CodePageRanges'),
            ('weightClass', 'OS2WeightClass'),
            ('widthClass', 'OS2WidthClass'),
            ('win', 'OS2Win'), ('vendorID', 'OS2VendorID'),
            ('versionString', 'NameVersion'), ('fsType', 'OS2Type'))
        for glyphs_prefix, ufo_prefix in opentype_attr_prefix_pairs:
            name = re.sub(
                '^' + glyphs_prefix, 'openType' + ufo_prefix, name)

        postscript_attrs = ('underlinePosition', 'underlineThickness')
        if name in postscript_attrs:
            name = 'postscript' + name[0].upper() + name[1:]

        # enforce that winAscent/Descent are positive, according to UFO spec
        if name.startswith('openTypeOS2Win') and value < 0:
            value = -value

        # The value of these could be a float, and ufoLib/defcon expect an int.
        if name in ('openTypeOS2WeightClass', 'openTypeOS2WidthClass'):
            value = int(value)

        if name == 'glyphOrder':
            # store the public.glyphOrder in lib.plist
            ufo.lib[PUBLIC_PREFIX + name] = value
        elif name == 'Filter':
            filter_struct = parse_glyphs_filter(value)
            if not filter_struct:
                continue
            if UFO2FT_FILTERS_KEY not in ufo.lib.keys():
                ufo.lib[UFO2FT_FILTERS_KEY] = []
            ufo.lib[UFO2FT_FILTERS_KEY].append(filter_struct)
        elif hasattr(ufo.info, name) and name not in non_info:
            # most OpenType table entries go in the info object
            setattr(ufo.info, name, value)
        else:
            # everything else gets dumped in the lib
            ufo.lib[GLYPHS_PREFIX + name] = value


def set_default_params(ufo):
    """ Set Glyphs.app's default parameters when different from ufo2ft ones.
    """
    # ufo2ft defaults to fsType Bit 2 ("Preview & Print embedding"), while
    # Glyphs.app defaults to Bit 3 ("Editable embedding")
    if ufo.info.openTypeOS2Type is None:
        ufo.info.openTypeOS2Type = [3]

    # Reference:
    # https://glyphsapp.com/content/1-get-started/2-manuals/1-handbook-glyphs-2-0/Glyphs-Handbook-2.3.pdf#page=200
    if ufo.info.postscriptUnderlineThickness is None:
        ufo.info.postscriptUnderlineThickness = 50
    if ufo.info.postscriptUnderlinePosition is None:
        ufo.info.postscriptUnderlinePosition = -100


def normalize_custom_param_name(name):
    """Replace curved quotes with straight quotes in a custom parameter name.
    These should be the only keys with problematic (non-ascii) characters,
    since they can be user-generated.
    """

    replacements = (
        (u'\u2018', "'"), (u'\u2019', "'"), (u'\u201C', '"'), (u'\u201D', '"'))
    for orig, replacement in replacements:
        name = name.replace(orig, replacement)
    return name


def parse_custom_params(font, misc_keys):
    """Parse customParameters into a list of <name, val> pairs."""

    params = []
    for p in font.customParameters:
        params.append((p.name, p.value))
    for key in misc_keys:
        try:
            val = getattr(font, key)
        except KeyError:
            continue
        if val is not None:
            params.append((key, val))
    return params


def set_family_user_data(ufo, user_data):
    """Set family-wide user data as Glyphs does."""

    for key in user_data.keys():
        ufo.lib[key] = user_data[key]


def set_master_user_data(ufo, user_data):
    """Set master-specific user data as Glyphs does."""

    if user_data:
        data = {}
        for key in user_data.keys():
            data[key] = user_data[key]
        ufo.lib[GLYPHS_PREFIX + 'fontMaster.userData'] = data


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
    master.id = ufo.lib[GLYPHS_PREFIX + 'fontMasterID']
    # TODO: all the other attributes
