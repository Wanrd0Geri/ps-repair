// 配方：adj_photo_filter
// 用途：照片滤镜调整层（带蒙版）：给局部统一色温（暖光灯笼周围加暖、夜景远处加冷）。
// 参数：
//   doc_id                int        默认=当前文档
//   rgb                   [r,g,b]    默认=[236,138,0]（接近 PS“加温滤镜 85”）
//   density               int        默认=25    1-100（%）
//   preserve_luminosity   bool       默认=true
//   selection / layer_id / expand_px / feather_px / clip / label   同 adj_curves
// 产出：图层「修_adj_photo_filter_<label>」（照片滤镜调整层 + 选区蒙版）；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py；读回描述符 Lab 颜色、density、preserveLuminosity 与输入一致）
// 费用/限制：本地、不扣积分；颜色内部转 Lab 传给 PS。

function run(args) {
  var doc = getDoc(args);
  var rgb = opt(args, 'rgb', [236, 138, 0]);
  var dens = Math.round(Number(opt(args, 'density', 25)));
  if (!(dens >= 1 && dens <= 100)) fail('BAD_ARG', 'density 1-100');
  rgbDesc(rgb);  // 校验
  var lab = rgbToLab(rgb);
  var c = new ActionDescriptor();
  c.putDouble(cTID('Lmnc'), lab[0]); c.putDouble(cTID('A   '), lab[1]); c.putDouble(cTID('B   '), lab[2]);
  var adj = new ActionDescriptor();
  adj.putObject(cTID('Clr '), cTID('LbCl'), c);
  adj.putInteger(cTID('Dnst'), dens);
  adj.putBoolean(cTID('PrsL'), !!opt(args, 'preserve_luminosity', true));
  return adjustmentFlow(doc, args, 'adj_photo_filter', function () { return makeAdjustmentLayer(sTID('photoFilter'), adj); });
}
