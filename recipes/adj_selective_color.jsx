// 配方：adj_selective_color
// 用途：可选颜色调整层（带蒙版）：只动某一色系的 CMYK 成分，如压青色天空里的洋红、给中性灰去偏色。
// 参数：
//   doc_id     int      默认=当前文档
//   colors     object   必填   {"reds":[c,m,y,k], "neutrals":[...], ...}，每项 -100..100（%）
//                              色系键：reds/yellows/greens/cyans/blues/magentas/whites/neutrals/blacks
//   method     str      默认="relative"   relative/absolute
//   selection / layer_id / expand_px / feather_px / clip / label   同 adj_curves
// 产出：图层「修_adj_selective_color_<label>」（可选颜色调整层 + 选区蒙版）；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py；读回描述符 method 与 CMYK 值与输入一致）
// 费用/限制：本地、不扣积分。

var SC_KEYS = { reds: 'Rds ', yellows: 'Ylws', greens: 'Grns', cyans: 'Cyns', blues: 'Bls ', magentas: 'Mgnt',
                whites: 'Whts', neutrals: 'Ntrl', blacks: 'Blks' };

function run(args) {
  var doc = getDoc(args);
  var colors = opt(args, 'colors', null);
  if (!colors) fail('BAD_ARG', 'colors 必填，如 {"neutrals":[0,-5,0,0]}');
  var method = { relative: 'Rltv', absolute: 'Absl' }[opt(args, 'method', 'relative')];
  if (!method) fail('BAD_ARG', 'method 只能是 relative/absolute');
  var list = new ActionList(), n = 0;
  for (var k in colors) {
    if (!colors.hasOwnProperty(k)) continue;
    if (!SC_KEYS[k]) fail('BAD_ARG', '未知色系 ' + k);
    var v = colors[k];
    if (!(v instanceof Array) || v.length != 4) fail('BAD_ARG', k + ' 需要 [c,m,y,k]');
    var c = new ActionDescriptor();
    c.putEnumerated(cTID('Clrs'), cTID('Clrs'), cTID(SC_KEYS[k]));
    c.putUnitDouble(cTID('Cyn '), cTID('#Prc'), Number(v[0]));
    c.putUnitDouble(cTID('Mgnt'), cTID('#Prc'), Number(v[1]));
    c.putUnitDouble(cTID('Ylw '), cTID('#Prc'), Number(v[2]));
    c.putUnitDouble(cTID('Blck'), cTID('#Prc'), Number(v[3]));
    list.putObject(cTID('ClrC'), c);
    n++;
  }
  if (!n) fail('BAD_ARG', 'colors 为空');
  var adj = new ActionDescriptor();
  adj.putEnumerated(sTID('presetKind'), sTID('presetKindType'), sTID('presetKindCustom'));
  adj.putEnumerated(cTID('Mthd'), cTID('CrcM'), cTID(method));
  adj.putList(cTID('ClrC'), list);
  return adjustmentFlow(doc, args, 'adj_selective_color', function () { return makeAdjustmentLayer(cTID('SlcC'), adj); });
}
