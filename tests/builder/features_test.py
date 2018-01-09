# coding=UTF-8
#
# Copyright 2016 Google Inc. All Rights Reserved.
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

import os
import pytest
from textwrap import dedent

import defcon

from glyphsLib import to_glyphs, to_designspace, to_ufos, classes


def make_font(features):
    ufo = defcon.Font()
    ufo.features = dedent(features)
    return ufo


def roundtrip(ufo, tmpdir):
    font = to_glyphs([ufo], minimize_ufo_diffs=True)
    filename = os.path.join(str(tmpdir), 'font.glyphs')
    font.save(filename)
    font = classes.GSFont(filename)
    ufo, = to_ufos(font)
    return font, ufo


def test_blank(tmpdir):
    ufo = defcon.Font()

    font, rtufo = roundtrip(ufo, tmpdir)

    assert not font.features
    assert not font.featurePrefixes
    assert not rtufo.features.text


# FIXME: (jany) fix in feaLib
@pytest.mark.xfail(
    reason='feaLib does not parse correctly a file with only comments')
def test_comment(tmpdir):
    ufo = defcon.Font()
    ufo.features.text = dedent('''\
        # Test
        # Lol
    ''')

    font, rtufo = roundtrip(ufo, tmpdir)

    assert not font.features
    assert len(font.featurePrefixes) == 1
    fp = font.featurePrefixes[0]
    assert fp.code == ufo.features.text
    assert not fp.automatic

    assert rtufo.features.text == ufo.features.text


def test_languagesystems(tmpdir):
    ufo = defcon.Font()
    # The sample has messed-up spacing because there was a problem with that
    ufo.features.text = dedent('''\
        # Blah
          languagesystem DFLT dflt; #Default
        languagesystem latn dflt;\t# Latin
        \tlanguagesystem arab URD; #\tUrdu
    ''')

    font, rtufo = roundtrip(ufo, tmpdir)

    assert not font.features
    assert len(font.featurePrefixes) == 1
    fp = font.featurePrefixes[0]
    assert fp.code == ufo.features.text[:-1]  # Except newline
    assert not fp.automatic

    assert rtufo.features.text == ufo.features.text


def test_classes(tmpdir):
    ufo = defcon.Font()
    # FIXME: (jany) no whitespace is preserved in this section
    ufo.features.text = dedent('''\
        @lc = [ a b ];

        @UC = [ A B ];

        @all = [ @lc @UC zero one ];

        @more = [ dot @UC colon @lc paren ];
    ''')

    font, rtufo = roundtrip(ufo, tmpdir)

    assert len(font.classes) == 4
    assert font.classes['lc'].code == 'a b'
    assert font.classes['UC'].code == 'A B'
    assert font.classes['all'].code == '@lc @UC zero one'
    assert font.classes['more'].code == 'dot @UC colon @lc paren'

    assert rtufo.features.text == ufo.features.text


def test_class_synonym(tmpdir):
    ufo = defcon.Font()
    ufo.features.text = dedent('''\
        @lc = [ a b ];

        @lower = @lc;
    ''')

    font, rtufo = roundtrip(ufo, tmpdir)

    assert len(font.classes) == 2
    assert font.classes['lc'].code == 'a b'
    assert font.classes['lower'].code == '@lc'

    # FIXME: (jany) should roundtrip
    assert rtufo.features.text == dedent('''\
        @lc = [ a b ];

        @lower = [ @lc ];
    ''')


@pytest.mark.xfail(reason='Fealib will always resolve includes')
# FIXME: (jany) what to do?
#    1. Have an option in feaLib to NOT follow includes and have an AST element
#       like "include statement". This is the easiest way to handle roundtrip
#       because we can have a GSFeaturePrefix with the include statement in it.
#    2. Always enforce that includes must be resolvable, and dispatch their
#       contents into GSFeaturePrefix, GSClass, GSFeature and so on. Very hard
#       to roundtrip because we lose the original include information (or we
#       need lots of bookkeeping)
def test_include(tmpdir):
    ufo = defcon.Font()
    ufo.features.text = dedent('''\
        include(../family.fea);
        # Blah
        include(../fractions.fea);
    ''')

    font, rtufo = roundtrip(ufo, tmpdir)

    assert len(font.featurePrefixes) == 1
    assert font.featurePrefixes[0].code == ufo.features.text

    assert rtufo.features.text == ufo.features.text


def test_standalone_lookup(tmpdir):
    ufo = defcon.Font()
    # FIXME: (jany) does not preserve whitespace before and after
    ufo.features.text = dedent('''\
        # start of default rules that are applied under all language systems.
        lookup HAS_I {
          sub f f i by f_f_i;
            sub f i by f_i;
        } HAS_I;
    ''')

    font, rtufo = roundtrip(ufo, tmpdir)

    assert len(font.featurePrefixes) == 1
    assert font.featurePrefixes[0].code.strip() == ufo.features.text.strip()

    assert rtufo.features.text == ufo.features.text


def test_feature(tmpdir):
    ufo = defcon.Font()
    # This sample is straight from the documentation at
    # http://www.adobe.com/devnet/opentype/afdko/topic_feature_file_syntax.html
    # FIXME: (jany) does not preserve whitespace before and after
    ufo.features.text = dedent('''\
        feature liga {
      # start of default rules that are applied under all language systems.
                lookup HAS_I {
                 sub f f i by f_f_i;
                 sub f i by f_i;
                } HAS_I;

                lookup NO_I {
                 sub f f l by f_f_l;
                 sub f f by f_f;
                } NO_I;

      # end of default rules that are applied under all language systems.

            script latn;
               language dflt;
      # default lookup for latn included under all languages for the latn script

                  sub f l by f_l;
               language DEU;
      # default lookups included under the DEU language..
                  sub s s by germandbls;   # This is also included.
               language TRK exclude_dflt;   # default lookups are excluded.
                lookup NO_I;             #Only this lookup is included under the TRK language

            script cyrl;
               language SRB;
                  sub c t by c_t; # this rule will apply only under script cyrl language SRB.
      } liga;
    ''')

    font, rtufo = roundtrip(ufo, tmpdir)

    assert len(font.features) == 1
    # Strip "feature liga {} liga;"
    code = ufo.features.text.splitlines()[1:-1]
    assert font.features[0].code.strip() == '\n'.join(code)

    assert rtufo.features.text.strip() == ufo.features.text.strip()


# TODO: add test with different features in different UFOs
# Assumption: all UFOs must have the same feature files, otherwise warning
# Use the feature file from the first UFO
