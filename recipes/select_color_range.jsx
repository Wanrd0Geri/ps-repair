// 配方：select_color_range
// 用途：“选择 > 色彩范围”：按取样颜色（人话：RGB + 容差）或预设（高光/中间调/阴影/红…）选区。
// 参数：
//   doc_id             int                默认=当前文档
//   sample_rgb         [r,g,b] 或 [[r,g,b],...]   取样色（0-255）；多个时取它们 Lab 的包围范围（= 取样时按住 Shift 加色）
//   fuzziness          int                默认=40   颜色容差 0-200
//   preset             str                与 sample_rgb 二选一：highlights/midtones/shadows/reds/yellows/greens/
//                                         cyans/blues/magentas/skin_tones
//   invert             bool               默认=false
//   within_selection   bool               默认=false   true=只在当前选区内找（PS 原生行为）；false=先取消选区
// 产出：选区；返回 bounds 与实际使用的 Lab 范围
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py：单色/多色取样、preset=highlights、within_selection）；
//   其余 preset 只是枚举值不同，未逐个验证。
// 费用/限制：本地、不扣积分；内部把 RGB 用 PS 的 SolidColor 转 Lab（按当前颜色设置），再传 ClrR 的 Mnm/Mxm。
//   找不到颜色时 found=false。

var PRESETS = { reds: 'Rds ', yellows: 'Ylws', greens: 'Grns', cyans: 'Cyns', blues: 'Bls ', magentas: 'Mgnt',
                highlights: 'Hghl', midtones: 'Mdtn', shadows: 'Shdw' };

function labDesc(v) {
  var d = new ActionDescriptor();
  d.putDouble(cTID('Lmnc'), v[0]); d.putDouble(cTID('A   '), v[1]); d.putDouble(cTID('B   '), v[2]);
  return d;
}

function run(args) {
  var doc = getDoc(args);
  if (!opt(args, 'within_selection', false)) doc.selection.deselect();
  var d = new ActionDescriptor(), out = {};
  var preset = opt(args, 'preset', null);
  if (preset) {
    if (preset == 'skin_tones') d.putEnumerated(cTID('Clrs'), cTID('Clrs'), sTID('skinTone'));
    else if (PRESETS[preset]) d.putEnumerated(cTID('Clrs'), cTID('Clrs'), cTID(PRESETS[preset]));
    else fail('BAD_ARG', '未知 preset：' + preset);
    out.preset = preset;
  } else {
    var s = opt(args, 'sample_rgb', null);
    if (!(s instanceof Array) || !s.length) fail('BAD_ARG', '需要 sample_rgb 或 preset');
    var samples = (s[0] instanceof Array) ? s : [s];
    var mn = [999, 999, 999], mx = [-999, -999, -999];
    for (var i = 0; i < samples.length; i++) {
      var lab = rgbToLab(samples[i]);
      for (var k = 0; k < 3; k++) { mn[k] = Math.min(mn[k], lab[k]); mx[k] = Math.max(mx[k], lab[k]); }
    }
    d.putInteger(cTID('Fzns'), Math.round(Number(opt(args, 'fuzziness', 40))));
    d.putObject(cTID('Mnm '), cTID('LbCl'), labDesc(mn));
    d.putObject(cTID('Mxm '), cTID('LbCl'), labDesc(mx));
    d.putInteger(sTID('colorModel'), 0);
    out.lab_min = [round2(mn[0]), round2(mn[1]), round2(mn[2])];
    out.lab_max = [round2(mx[0]), round2(mx[1]), round2(mx[2])];
  }
  if (opt(args, 'invert', false)) d.putBoolean(cTID('Invr'), true);
  executeAction(cTID('ClrR'), d, DialogModes.NO);
  out.bounds = selBounds(doc);
  out.found = out.bounds !== null;
  return out;
}
