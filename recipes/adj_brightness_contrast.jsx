// 配方：adj_brightness_contrast
// 用途：亮度/对比度调整层（带蒙版）：快速整体或局部提亮、压对比。
// 参数：
//   doc_id       int    默认=当前文档
//   brightness   int    默认=0   -150..150
//   contrast     int    默认=0   -50..100
//   legacy       bool   默认=false   旧版算法（会剪切高光/阴影，一般不用）
//   selection / layer_id / expand_px / feather_px / clip / label   同 adj_curves
// 产出：图层「修_adj_brightness_contrast_<label>」（调整层 + 选区蒙版）；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分。

function run(args) {
  var doc = getDoc(args);
  var b = Math.round(Number(opt(args, 'brightness', 0))), c = Math.round(Number(opt(args, 'contrast', 0)));
  if (!(b >= -150 && b <= 150 && c >= -50 && c <= 100)) fail('BAD_ARG', 'brightness -150..150，contrast -50..100');
  var adj = new ActionDescriptor();
  adj.putInteger(cTID('Brgh'), b);
  adj.putInteger(cTID('Cntr'), c);
  adj.putBoolean(sTID('useLegacy'), !!opt(args, 'legacy', false));
  return adjustmentFlow(doc, args, 'adj_brightness_contrast', function () { return makeAdjustmentLayer(cTID('BrgC'), adj); });
}
