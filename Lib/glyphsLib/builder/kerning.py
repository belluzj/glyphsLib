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
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

GROUP_KEYS = {
    '1': 'rightKerningGroup',
    '2': 'leftKerningGroup'}

UFO_KERN_GROUP_PATTERN = re.compile('^public\\.kern([12])\\.(.*)$')


def to_ufo_kerning(self, ufo, kerning_data):
    """Add .glyphs kerning to an UFO."""

    warning_msg = 'Non-existent glyph class %s found in kerning rules.'
    class_glyph_pairs = []

    for left, pairs in kerning_data.items():
        match = re.match(r'@MMK_L_(.+)', left)
        left_is_class = bool(match)
        if left_is_class:
            left = 'public.kern1.%s' % match.group(1)
            if left not in ufo.groups:
                # logger.warn(warning_msg % left)
                pass
        for right, kerning_val in pairs.items():
            match = re.match(r'@MMK_R_(.+)', right)
            right_is_class = bool(match)
            if right_is_class:
                right = 'public.kern2.%s' % match.group(1)
                if right not in ufo.groups:
                    # logger.warn(warning_msg % right)
                    pass
            if left_is_class != right_is_class:
                if left_is_class:
                    pair = (left, right, True)
                else:
                    pair = (right, left, False)
                class_glyph_pairs.append(pair)
            ufo.kerning[left, right] = kerning_val

    seen = {}
    for classname, glyph, is_left_class in reversed(class_glyph_pairs):
        _remove_rule_if_conflict(ufo, seen, classname, glyph, is_left_class)


def to_glyphs_kerning(self, ufo, master):
    """Add UFO kerning to GSFontMaster."""
    for (left, right), value in ufo.kerning.items():
        left_match = UFO_KERN_GROUP_PATTERN.match(left)
        right_match = UFO_KERN_GROUP_PATTERN.match(right)
        if left_match:
            left = '@MMK_L_{}'.format(left_match.group(2))
        if right_match:
            right = '@MMK_R_{}'.format(right_match.group(2))
        self.font.setKerningForPair(master.id, left, right, value)
    # FIXME: (jany) handle conflicts?


def _remove_rule_if_conflict(ufo, seen, classname, glyph, is_left_class):
    """Check if a class-to-glyph kerning rule has a conflict with any existing
    rule in `seen`, and remove any conflicts if they exist.
    """
    original_pair = (classname, glyph) if is_left_class else (glyph, classname)
    val = ufo.kerning[original_pair]
    rule = original_pair + (val,)

    try:
        old_glyphs = ufo.groups[classname]
    except KeyError:
        # This can happen. The main function `to_ufo_kerning` prints a warning.
        return

    new_glyphs = []
    for member in old_glyphs:
        pair = (member, glyph) if is_left_class else (glyph, member)
        existing_rule = seen.get(pair)
        if (existing_rule is not None and
                existing_rule[-1] != val and
                pair not in ufo.kerning):
            logger.warn(
                'Conflicting kerning rules found in %s master for glyph pair '
                '"%s, %s" (%s and %s), removing pair from latter rule' %
                ((ufo.info.styleName,) + pair + (existing_rule, rule)))
        else:
            new_glyphs.append(member)
            seen[pair] = rule

    if new_glyphs != old_glyphs:
        del ufo.kerning[original_pair]
        for member in new_glyphs:
            pair = (member, glyph) if is_left_class else (glyph, member)
            ufo.kerning[pair] = val


def to_ufo_glyph_groups(self, kerning_groups, glyph_data):
    """Add a glyph to its kerning groups, creating new groups if necessary."""

    glyph_name = glyph_data.name
    for side, group_key in GROUP_KEYS.items():
        group = getattr(glyph_data, group_key)
        if group is None or len(group) == 0:
            continue
        group = 'public.kern%s.%s' % (side, group)
        kerning_groups[group] = kerning_groups.get(group, []) + [glyph_name]


def to_glyphs_glyph_groups(self, kerning_groups, glyph):
    """Write kerning groups to the GSGlyph.
    Uses the ouput of to_glyphs_kerning_groups.
    """
    for group_key, group_name in kerning_groups.items():
        setattr(glyph, group_key, group_name)


def to_ufo_kerning_groups(self, ufo, kerning_groups):
    """Add kerning groups to an UFO."""

    for name, glyphs in kerning_groups.items():
        ufo.groups[name] = glyphs


def to_glyphs_kerning_groups(self, ufo):
    """Extract all kerning group information from UFO.
    Return a dict {glyph name: dict {rightKerningGroup: leftKerningGroup: }}
    """
    result = defaultdict(dict)
    for group, members in ufo.groups.items():
        match = UFO_KERN_GROUP_PATTERN.match(group)
        if not match:
            continue
        side = match.group(1)
        group_name = match.group(2)
        for glyph_name in members:
            result[glyph_name][GROUP_KEYS[side]] = group_name

    return result
