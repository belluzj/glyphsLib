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
import logging
logger = logging.getLogger(__name__)

from defcon import Color

import glyphsLib.glyphdata
from .common import to_ufo_time, from_ufo_time
from .constants import (GLYPHLIB_PREFIX, GLYPHS_COLORS, GLYPHS_PREFIX,
                        PUBLIC_PREFIX)

SCRIPT_LIB_KEY = GLYPHLIB_PREFIX + 'script'
ORIGINAL_WIDTH_KEY = GLYPHLIB_PREFIX + 'originalWidth'


def to_ufo_glyph(self, ufo_glyph, layer, glyph):
    """Add .glyphs metadata, paths, components, and anchors to a glyph."""
    from glyphsLib import glyphdata  # Expensive import

    uval = glyph.unicode
    if uval is not None:
        ufo_glyph.unicode = int(uval, 16)
        # FIXME: (jany) handle several unicodes
        # https://github.com/googlei18n/glyphsLib/issues/216
    note = glyph.note
    if note is not None:
        ufo_glyph.note = note
    last_change = glyph.lastChange
    if last_change is not None:
        ufo_glyph.lib[GLYPHLIB_PREFIX + 'lastChange'] = to_ufo_time(last_change)
    color_index = glyph.color
    if color_index is not None:
        ufo_glyph.lib[GLYPHLIB_PREFIX + 'ColorIndex'] = color_index
        color_tuple = None
        if isinstance(color_index, list):
            if not all(i in range(0, 256) for i in color_index):
                logger.warn('Invalid color tuple {} for glyph {}. '
                            'Values must be in range 0-255'.format(color_index, glyph.name))
            else:
                color_tuple = ','.join('{0:.4f}'.format(i/255) if i in range(1, 255) else str(i//255) for i in color_index)
        elif isinstance(color_index, int) and color_index in range(len(GLYPHS_COLORS)):
            color_tuple = GLYPHS_COLORS[color_index]
        else:
            logger.warn('Invalid color index {} for {}'.format(color_index, glyph.name))
        if color_tuple is not None:
            ufo_glyph.lib[PUBLIC_PREFIX + 'markColor'] = color_tuple
    export = glyph.export
    if not export:
        ufo_glyph.lib[GLYPHLIB_PREFIX + 'Export'] = export
    # FIXME: (jany) next line should be an API of GSGlyph?
    glyphinfo = glyphdata.get_glyph(ufo_glyph.name)
    production_name = glyph.production or glyphinfo.production_name
    if production_name != ufo_glyph.name:
        postscriptNamesKey = PUBLIC_PREFIX + 'postscriptNames'
        if postscriptNamesKey not in ufo_glyph.font.lib:
            ufo_glyph.font.lib[postscriptNamesKey] = dict()
        ufo_glyph.font.lib[postscriptNamesKey][ufo_glyph.name] = production_name

    for key in ['leftMetricsKey', 'rightMetricsKey', 'widthMetricsKey']:
        value = getattr(layer, key, None)
        if value:
            ufo_glyph.lib[GLYPHLIB_PREFIX + 'layer.' + key] = value
        value = getattr(glyph, key, None)
        if value:
            ufo_glyph.lib[GLYPHLIB_PREFIX + 'glyph.' + key] = value

    if glyph.script is not None:
        ufo_glyph.lib[SCRIPT_LIB_KEY] = glyph.script

    # if glyph contains custom 'category' and 'subCategory' overrides, store
    # them in the UFO glyph's lib
    category = glyph.category
    if category is None:
        category = glyphinfo.category
    else:
        ufo_glyph.lib[GLYPHLIB_PREFIX + 'category'] = category
    subCategory = glyph.subCategory
    if subCategory is None:
        subCategory = glyphinfo.subCategory
    else:
        ufo_glyph.lib[GLYPHLIB_PREFIX + 'subCategory'] = subCategory

    # load width before background, which is loaded with lib data
    width = layer.width
    if width is None:
        pass
    elif category == 'Mark' and subCategory == 'Nonspacing' and width > 0:
        # zero the width of Nonspacing Marks like Glyphs.app does on export
        # TODO: check for customParameter DisableAllAutomaticBehaviour
        # FIXME: (jany) also don't do that when rt UFO -> glyphs -> UFO
        ufo_glyph.lib[ORIGINAL_WIDTH_KEY] = width
        ufo_glyph.width = 0
    else:
        ufo_glyph.width = width

    self.to_ufo_background_image(ufo_glyph, layer)
    self.to_ufo_guidelines(ufo_glyph, layer)
    self.to_ufo_glyph_background(ufo_glyph, layer)
    self.to_ufo_annotations(ufo_glyph, layer)
    self.to_ufo_hints(ufo_glyph, layer)
    self.to_ufo_glyph_user_data(ufo_glyph.font, glyph)
    self.to_ufo_layer_user_data(ufo_glyph, layer)
    self.to_ufo_smart_component_axes(ufo_glyph, glyph)

    self.to_ufo_paths(ufo_glyph, layer)
    self.to_ufo_components(ufo_glyph, layer)
    self.to_ufo_glyph_anchors(ufo_glyph, layer.anchors)


def to_glyphs_glyph(self, ufo_glyph, ufo_layer, master):
    """Add UFO glif metadata, paths, components, and anchors to a GSGlyph.
    If the matching GSGlyph does not exist, then it is created,
    else it is updated with the new data.
    In all cases, a matching GSLayer is created in the GSGlyph to hold paths.
    """

    # FIXME: (jany) split between glyph and layer attributes
    #        have a write the first time, compare the next times for glyph
    #        always write for the layer

    if ufo_glyph.name in self.font.glyphs:
        glyph = self.font.glyphs[ufo_glyph.name]
    else:
        glyph = self.glyphs_module.GSGlyph(name=ufo_glyph.name)
        # FIXME: (jany) ordering?
        self.font.glyphs.append(glyph)

    uval = ufo_glyph.unicode
    if uval is not None:
        glyph.unicode = '{:04X}'.format(uval)
        # FIXME: (jany) handle several unicodes
        # https://github.com/googlei18n/glyphsLib/issues/216
    note = ufo_glyph.note
    if note is not None:
        glyph.note = note
    if GLYPHLIB_PREFIX + 'lastChange' in ufo_glyph.lib:
        last_change = ufo_glyph.lib[GLYPHLIB_PREFIX + 'lastChange']
        glyph.lastChange = from_ufo_time(last_change)
    if ufo_glyph.markColor:
        if GLYPHLIB_PREFIX + 'ColorIndex' in ufo_glyph.lib:
            color_index = ufo_glyph.lib[GLYPHLIB_PREFIX + 'ColorIndex']
            if ufo_glyph.markColor == GLYPHS_COLORS[color_index]:
                # Still coherent
                glyph.color = color_index
            else:
                glyph.color = _to_glyphs_color_index(self, ufo_glyph.markColor)
        else:
            glyph.color = _to_glyphs_color_index(self, ufo_glyph.markColor)
    if GLYPHLIB_PREFIX + 'Export' in ufo_glyph.lib:
        glyph.export = ufo_glyph.lib[GLYPHLIB_PREFIX + 'Export']
    ps_names_key = PUBLIC_PREFIX + 'postscriptNames'
    if (ps_names_key in ufo_glyph.font.lib and
            ufo_glyph.name in ufo_glyph.font.lib[ps_names_key]):
        glyph.production = ufo_glyph.font.lib[ps_names_key][ufo_glyph.name]
        # FIXME: (jany) maybe put something in glyphinfo? No, it's readonly
        #        maybe don't write in glyph.production if glyphinfo already
        #        has something
        # glyphinfo = glyphsLib.glyphdata.get_glyph(ufo_glyph.name)
        # production_name = glyph.production or glyphinfo.production_name

    glyphinfo = glyphsLib.glyphdata.get_glyph(ufo_glyph.name)

    layer = self.to_glyphs_layer(ufo_layer, glyph, master)

    for key in ['leftMetricsKey', 'rightMetricsKey', 'widthMetricsKey']:
        for prefix, object in (('glyph.', glyph), ('layer.', layer)):
            full_key = GLYPHLIB_PREFIX + prefix + key
            if full_key in ufo_glyph.lib:
                value = ufo_glyph.lib[full_key]
                setattr(object, key, value)

    if SCRIPT_LIB_KEY in ufo_glyph.lib:
        glyph.script = ufo_glyph.lib[SCRIPT_LIB_KEY]

    if GLYPHLIB_PREFIX + 'category' in ufo_glyph.lib:
        # TODO: (jany) store category only if different from glyphinfo?
        category = ufo_glyph.lib[GLYPHLIB_PREFIX + 'category']
        glyph.category = category
    else:
        category = glyphinfo.category
    if GLYPHLIB_PREFIX + 'subCategory' in ufo_glyph.lib:
        sub_category = ufo_glyph.lib[GLYPHLIB_PREFIX + 'subCategory']
        glyph.subCategory = sub_category
    else:
        sub_category = glyphinfo.subCategory

    # load width before background, which is loaded with lib data
    layer.width = ufo_glyph.width
    if category == 'Mark' and sub_category == 'Nonspacing' and layer.width == 0:
        # Restore originalWidth
        if ORIGINAL_WIDTH_KEY in ufo_glyph.lib:
            layer.width = ufo_glyph.lib[ORIGINAL_WIDTH_KEY]
            # TODO: check for customParameter DisableAllAutomaticBehaviour?

    self.to_glyphs_background_image(ufo_glyph, layer)
    self.to_glyphs_guidelines(ufo_glyph, layer)
    self.to_glyphs_annotations(ufo_glyph, layer)
    self.to_glyphs_hints(ufo_glyph, layer)
    self.to_glyphs_glyph_user_data(ufo_glyph.font, glyph)
    self.to_glyphs_layer_user_data(ufo_glyph, layer)
    self.to_glyphs_smart_component_axes(ufo_glyph, glyph)

    self.to_glyphs_paths(ufo_glyph, layer)
    self.to_glyphs_components(ufo_glyph, layer)
    self.to_glyphs_glyph_anchors(ufo_glyph, layer)


def to_ufo_glyph_background(self, glyph, layer):
    """Set glyph background."""

    if not layer.hasBackground:
        return

    background = layer.background

    # FIXME: (jany) move most of this to layers.py
    if glyph.layer.name != 'public.default':
        layer_name = glyph.layer.name + '.background'
    else:
        layer_name = 'public.background'
    font = glyph.font
    if layer_name not in font.layers:
        layer = font.newLayer(layer_name)
    else:
        layer = font.layers[layer_name]
    new_glyph = layer.newGlyph(glyph.name)
    new_glyph.width = glyph.width

    self.to_ufo_background_image(new_glyph, background)
    self.to_ufo_paths(new_glyph, background)
    self.to_ufo_components(new_glyph, background)
    self.to_ufo_glyph_anchors(new_glyph, background.anchors)
    self.to_ufo_guidelines(new_glyph, background)


def _to_glyphs_color_index(self, color):
    # color is a defcon Color
    index, _ = min(
        enumerate(GLYPHS_COLORS),
        key=lambda _, glyphs_color: _rgb_distance(color, Color(glyphs_color)))
    return index
    # TODO: (jany) remove color approximation, actually it's possible to store
    #    arbitrary colors in Glyphs


def _rgb_distance(c1, c2):
    # https://en.wikipedia.org/wiki/Color_difference
    rmean = float(c1.r+c2.r) / 2
    dr = c1.r - c2.r
    dg = c1.g - c2.g
    db = c1.b - c2.b
    return (2 + rmean)*dr*dr + 4*dg*dg + (3 - rmean)*db*db
