// 配方：adj_color_balance
// 用途：色彩平衡调整层（带蒙版）：分阴影/中间调/高光推冷暖，统一局部色温。
// 参数：
//   doc_id                int         默认=当前文档
//   shadows               [c,m,y]     默认=[0,0,0]   每项 -100..100：青(-)↔红(+)、洋红(-)↔绿(+)、黄(-)↔蓝(+)
//   midtones              [c,m,y]     默认=[0,0,0]
//   highlights            [c,m,y]     默认=[0,0,0]
//   preserve_luminosity   bool        默认=true
//   selection / layer_id / expand_px / feather_px / clip / label   同 adj_curves
// 产出：图层「修_adj_color_balance_<label>」（色彩平衡调整层 + 选区蒙版）；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分。

function triple(v, name) {
  v = v || [0, 0, 0];
  if (!(v instanceof Array) || v.length != 3) fail('BAD_ARG', name + ' 需要 [c,m,y]');
  var l = new ActionList();
  for (var i = 0; i < 3; i++) {
    var n = Math.round(Number(v[i]));
    if (!(n >= -100 && n <= 100)) fail('BAD_ARG', name + ' 每项 -100..100');
    l.putInteger(n);
  }
  return l;
}

function run(args) {
  var doc = getDoc(args);
  var adj = new ActionDescriptor();
  adj.putList(cTID('ShdL'), triple(opt(args, 'shadows', null), 'shadows'));
  adj.putList(cTID('MdtL'), triple(opt(args, 'midtones', null), 'midtones'));
  adj.putList(cTID('HghL'), triple(opt(args, 'highlights', null), 'highlights'));
  adj.putBoolean(cTID('PrsL'), !!opt(args, 'preserve_luminosity', true));
  return adjustmentFlow(doc, args, 'adj_color_balance', function () { return makeAdjustmentLayer(cTID('ClrB'), adj); });
}
