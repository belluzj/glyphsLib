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

from glyphsLib.util import clear_data, cast_to_number_or_bool, \
    bin_to_int_list, int_list_to_bin
from .filters import parse_glyphs_filter, write_glyphs_filter
from .constants import GLYPHLIB_PREFIX, GLYPHS_PREFIX, PUBLIC_PREFIX, \
    CODEPAGE_RANGES, REVERSE_CODEPAGE_RANGES, UFO2FT_FILTERS_KEY

"""Set Glyphs custom parameters in UFO info or lib, where appropriate.

Custom parameter data can be pre-parsed out of Glyphs data and provided via
the `parsed` argument, otherwise `data` should be provided and will be
parsed. The `parsed` option is provided so that custom params can be popped
from Glyphs data once and used several times; in general this is used for
debugging purposes (to detect unused Glyphs data).

The `non_info` argument can be used to specify potential UFO info attributes
which should not be put in UFO info.
"""


def identity(value):
    return value


class ParamHandler(object):
    def __init__(self, glyphs_name, ufo_name=None,
                 ufo_prefix=GLYPHS_PREFIX, ufo_info=True,
                 value_to_ufo=identity, value_to_glyphs=identity):
        self.glyphs_name = glyphs_name
        # By default, they have the same name in both
        self.ufo_name = ufo_name or glyphs_name
        self.ufo_prefix = ufo_prefix
        self.ufo_info = ufo_info
        # Value transformation functions
        self.value_to_ufo = value_to_ufo
        self.value_to_glyphs = value_to_glyphs

    def glyphs_names(self):
        # Just in case one handler covers several names
        return (self.glyphs_name,)

    def ufo_names(self):
        return (self.ufo_name,)

    # By default, the parameter is read from/written to:
    #  - the Glyphs object's customParameters
    #  - the UFO's info object if it has a matching attribute, else the lib
    def to_glyphs(self, glyphs, ufo):
        ufo_value = self._read_from_ufo(ufo)
        if ufo_value is None:
            return
        glyphs_value = self.value_to_glyphs(ufo_value)
        self._write_to_glyphs(glyphs, glyphs_value)

    def to_ufo(self, glyphs, ufo):
        glyphs_value = self._read_from_glyphs(glyphs)
        if glyphs_value is None:
            return
        ufo_value = self.value_to_ufo(glyphs_value)
        self._write_to_ufo(ufo, ufo_value)

    def _read_from_glyphs(self, glyphs):
        return glyphs.customParameters[self.glyphs_name]

    def _write_to_glyphs(self, glyphs, value):
        glyphs.customParameters[self.glyphs_name] = value

    def _read_from_ufo(self, ufo):
        if self.ufo_info and hasattr(ufo.info, self.ufo_name):
            return getattr(ufo.info, self.ufo_name)
        else:
            return ufo.lib[self.ufo_prefix + self.ufo_name]

    def _write_to_ufo(self, ufo, value):
        if self.ufo_info and hasattr(ufo.info, self.ufo_name):
            # most OpenType table entries go in the info object
            setattr(ufo.info, self.ufo_name, value)
        else:
            # everything else gets dumped in the lib
            ufo.lib[self.ufo_prefix + self.ufo_name] = value


KNOWN_FAMILY_PARAM_HANDLERS = []
KNOWN_FAMILY_PARAM_GLYPHS_NAMES = set()
KNOWN_MASTER_PARAM_HANDLERS = []
KNOWN_MASTER_PARAM_GLYPHS_NAMES = set()
KNOWN_PARAM_UFO_NAMES = set()


def register(scope, handler):
    if scope == 'family':
        KNOWN_FAMILY_PARAM_HANDLERS.append(handler)
        KNOWN_FAMILY_PARAM_GLYPHS_NAMES.update(handler.glyphs_names())
    elif scope == 'master':
        KNOWN_MASTER_PARAM_HANDLERS.append(handler)
        KNOWN_MASTER_PARAM_GLYPHS_NAMES.update(handler.glyphs_names())
    else:
        raise RuntimeError
    KNOWN_PARAM_UFO_NAMES.update(handler.ufo_names())


# FIXME: (jany) apparently these might only be prefixes, find the list of full names
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
    ('vendorID', 'OS2VendorID'),
    ('versionString', 'NameVersion'), ('fsType', 'OS2Type'))
for glyphs_name, ufo_name in opentype_attr_prefix_pairs:
    full_ufo_name = 'openType' + ufo_name
    # FIXME: (jany) family or master?
    register('family', ParamHandler(glyphs_name, full_ufo_name))

# convert code page numbers to OS/2 ulCodePageRange bits
# FIXME: (jany) family or master?
register('family', ParamHandler(
    glyphs_name='codePageRanges',
    ufo_name='openTypeOS2CodePageRanges',
    value_to_ufo=lambda value: [CODEPAGE_RANGES[v] for v in value],
    value_to_glyphs=lambda value: [REVERSE_CODEPAGE_RANGES[v] for v in value]
))

# enforce that winAscent/Descent are positive, according to UFO spec
for glyphs_name in ('winAscent', 'winDescent'):
    ufo_name = 'openTypeOS2W' + glyphs_name[1:]
    # FIXME: (jany) family or master?
    register('family', ParamHandler(
        glyphs_name, ufo_name,
        value_to_ufo=lambda value: -abs(value),
        value_to_glyphs=abs,
    ))

# The value of these could be a float, and ufoLib/defcon expect an int.
for glyphs_name in ('weightClass', 'widthClass'):
    ufo_name = 'openTypeOS2W' + glyphs_name[1:]
    # FIXME: (jany) family or master?
    register('family', ParamHandler(glyphs_name, ufo_name, value_to_ufo=int))


# convert Glyphs' GASP Table to UFO openTypeGaspRangeRecords
def to_ufo_gasp_table(value):
    # XXX maybe the parser should cast the gasp values to int?
    value = {int(k): int(v) for k, v in value.items()}
    gasp_records = []
    # gasp range records must be sorted in ascending rangeMaxPPEM
    for max_ppem, gasp_behavior in sorted(value.items()):
        gasp_records.append({
            'rangeMaxPPEM': max_ppem,
            'rangeGaspBehavior': bin_to_int_list(gasp_behavior)})
    return gasp_records


def to_glyphs_gasp_table(value):
    return {
        record['rangeMaxPPEM']: int_list_to_bin(record['rangeGaspBehavior'])
        for record in value
    }

register('family', ParamHandler(
    glyphs_name='GASP Table',
    ufo_name='openTypeGaspRangeRecords',
    value_to_ufo=to_ufo_gasp_table,
    value_to_glyphs=to_glyphs_gasp_table,
))


class MiscParamHandler(ParamHandler):
    def read_from_glyphs(self, glyphs):
        return getattr(glyphs, self.glyphs_name)

    def write_to_glyphs(self, glyphs, value):
        setattr(glyphs, self.glyphs_name, value)


register('family', MiscParamHandler(glyphs_name='DisplayStrings'))
register('family', MiscParamHandler(glyphs_name='disablesAutomaticAlignment'))

# deal with any Glyphs naming quirks here
register('family', MiscParamHandler(
    glyphs_name='disablesNiceNames',
    ufo_name='useNiceNames',
    value_to_ufo=lambda value: int(not value),
    value_to_glyphs=lambda value: not bool(value)
))

for number in ('', '1', '2', '3'):
    register('master', MiscParamHandler('customName' + number, ufo_info=False))
    register('master', MiscParamHandler('customValue' + number,
                                        ufo_info=False))
register('master', MiscParamHandler('weightValue', ufo_info=False))
register('master', MiscParamHandler('widthValue', ufo_info=False))


class OS2SelectionParamHandler(object):
    flags = (
        ('Use Typo Metrics', 7),
        ('Has WWS Names', 8),
    )

    def glyphs_names(self):
        return [flag[0] for flag in flags]

    def ufo_names(self):
        return ('openTypeOS2Selection',)

    def to_glyphs(self, glyphs, ufo):
        ufo_flags = ufo.info.openTypeOS2Selection
        if ufo_flags is None:
            return
        for glyphs_name, value in self.flags:
            if value in ufo_flags:
                glyphs.customParameters[glyphs_name] = True

    def to_ufo(self, glyphs, ufo):
        for glyphs_name, value in self.flags:
            if glyphs.customParameters[glyphs_name]:
                if ufo.info.openTypeOS2Selection is None:
                    ufo.info.openTypeOS2Selection = []
                ufo.info.openTypeOS2Selection.append(value)

# FIXME: (jany) master or family?
register('family', OS2SelectionParamHandler())

# Postscript attributes
postscript_attrs = ('underlinePosition', 'underlineThickness')
for glyphs_name in postscript_attrs:
    ufo_name = 'postscript' + name[0].upper() + name[1:]
    # FIXME: (jany) master or family?
    register('family', ParamHandler(glyphs_name, ufo_name))

# store the public.glyphOrder in lib.plist
# FIXME: (jany) master or family?
register('family', ParamHandler('glyphOrder', ufo_prefix=PUBLIC_PREFIX))


class FilterParamHandler(ParamHandler):
    def __init__(self):
        super(FilterParamHandler, self).__init__(
            glyphs_name='Filter',
            ufo_name=UFO2FT_FILTERS_KEY,
            ufo_prefix='',
            value_to_ufo=parse_glyphs_filter,
            value_to_glyphs=write_glyphs_filter,
        )

    # Don't overwrite, append instead
    def _write_to_ufo(self, ufo, value):
        if self.ufo_name not in ufo.lib.keys():
            ufo.lib[self.ufo_name] = []
        ufo.lib[self.ufo_name].append(value)

# FIXME: (jany) maybe BOTH master AND family?
register('master', FilterParamHandler)


def to_ufo_custom_params(context, ufo, master):
    # Handle known parameters
    for handler in KNOWN_FAMILY_PARAM_HANDLERS:
        handler.to_ufo(context.font, ufo)
    for handler in KNOWN_MASTER_PARAM_HANDLERS:
        handler.to_ufo(master, ufo)

    # Handle unknown parameters
    for name, value in context.font.customParameters:
        name = normalize_custom_param_name(name)
        if name in KNOWN_FAMILY_PARAM_GLYPHS_NAMES:
            continue
        ufo.lib[GLYPHS_PREFIX + name] = value
    for name, value in master.customParameters:
        name = normalize_custom_param_name(name)
        if name in KNOWN_MASTER_PARAM_GLYPHS_NAMES:
            continue
        ufo.lib[GLYPHS_PREFIX + name] = value

    set_default_params(ufo)


def to_glyphs_family_custom_params(context, ufo):
    # Handle known parameters
    for handler in KNOWN_FAMILY_PARAM_HANDLERS:
        handler.to_glyphs(context.font, ufo)

    # Handle unknown parameters
    _to_glyphs_unknown_parameters(context.font, ufo)

    # FIXME: (jany) do something about default values?


def to_glyphs_master_custom_params(context, ufo, master):
    # Handle known parameters
    for handler in KNOWN_MASTER_PARAM_HANDLERS:
        handler.to_glyphs(context.font, ufo)

    # Handle unknown parameters
    _to_glyphs_unknown_parameters(master, ufo)

    # FIXME: (jany) do something about default values?


def _to_glyphs_unknown_parameters(glyphs, ufo):
    for name, value in ufo.info:
        name = normalize_custom_param_name(name)
        if name not in KNOWN_UFO_INFO_PARAM_NAMES:
            # TODO: (jany)
            pass

    for name, value in ufo.lib:
        name = normalize_custom_param_name(name)
        if name not in KNOWN_UFO_LIB_PARAM_NAMES:
            # TODO: (jany)
            pass


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
