// 配方：adj_hue_sat
// 用途：色相/饱和度调整层（带蒙版）：压局部过饱和、统一色相、去色，或“着色”整体染色。
// 参数：
//   doc_id       int      默认=当前文档
//   hue          int      默认=0   -180..180（colorize 时 0..360）
//   saturation   int      默认=0   -100..100（colorize 时 0..100）
//   lightness    int      默认=0   -100..100
//   colorize     bool     默认=false
//   selection / layer_id / expand_px / feather_px / clip / label   同 adj_curves
// 产出：图层「修_adj_hue_sat_<label>」（色相/饱和度调整层 + 选区蒙版）；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py：普通与 colorize；分色相范围未实现）
// 费用/限制：本地、不扣积分；只调“全图”主通道，想只动某个颜色先用 select_color_range 做选区。

function run(args) {
  var doc = getDoc(args);
  var colorize = !!opt(args, 'colorize', false);
  var h = Math.round(Number(opt(args, 'hue', 0))), s = Math.round(Number(opt(args, 'saturation', 0))), l = Math.round(Number(opt(args, 'lightness', 0)));
  if (colorize ? !(h >= 0 && h <= 360 && s >= 0 && s <= 100) : !(h >= -180 && h <= 180 && s >= -100 && s <= 100))
    fail('BAD_ARG', 'hue/saturation 超出范围');
  if (!(l >= -100 && l <= 100)) fail('BAD_ARG', 'lightness -100..100');
  var a = new ActionDescriptor();
  a.putInteger(cTID('H   '), h); a.putInteger(cTID('Strt'), s); a.putInteger(cTID('Lght'), l);
  var list = new ActionList(); list.putObject(cTID('Hst2'), a);
  var adj = new ActionDescriptor();
  adj.putEnumerated(sTID('presetKind'), sTID('presetKindType'), sTID('presetKindCustom'));
  adj.putBoolean(cTID('Clrz'), colorize);
  adj.putList(cTID('Adjs'), list);
  return adjustmentFlow(doc, args, 'adj_hue_sat', function () { return makeAdjustmentLayer(cTID('HStr'), adj); });
}
