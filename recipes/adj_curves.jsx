// 配方：adj_curves
// 用途：曲线调整层（带蒙版）：局部提亮/压暗、拉对比、分通道校色。
// 参数：
//   doc_id       int                 默认=当前文档
//   points       [[in,out],...]      复合通道曲线点（0-255）；没给 0/255 端点时自动补 [0,0]、[255,255]
//   channels     {"rgb":[...],"red":[...],"green":[...],"blue":[...]}   分通道（与 points 二选一，可同时给 rgb）
//   selection    选区                默认=沿用当前选区；无选区=全图
//   layer_id     int                 默认=当前图层   新层插在它上方
//   expand_px    int                 默认=0
//   feather_px   number              默认=0
//   clip         bool                默认=false
//   label        str                 默认=""
// 产出：图层「修_adj_curves_<label>」（曲线调整层 + 选区蒙版）；结束后取消选区；返回读回的曲线点
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py 断言区内变化、区外不变；读回描述符：复合+蓝通道曲线点与输入一致）
// 费用/限制：本地、不扣积分。

var CURVE_CH = { rgb: 'Cmps', red: 'Rd  ', green: 'Grn ', blue: 'Bl  ' };

function normPoints(p) {
  if (!(p instanceof Array) || p.length < 1) fail('BAD_ARG', '曲线点需要 [[in,out],...]');
  var pts = [], has0 = false, has255 = false;
  for (var i = 0; i < p.length; i++) {
    var x = Number(p[i][0]), y = Number(p[i][1]);
    if (!(x >= 0 && x <= 255 && y >= 0 && y <= 255)) fail('BAD_ARG', '曲线点超出 0-255：' + p[i]);
    if (x == 0) has0 = true;
    if (x == 255) has255 = true;
    pts.push([x, y]);
  }
  if (!has0) pts.unshift([0, 0]);
  if (!has255) pts.push([255, 255]);
  pts.sort(function (a, b) { return a[0] - b[0]; });
  return pts;
}

function run(args) {
  var doc = getDoc(args);
  var chans = opt(args, 'channels', null) || { rgb: opt(args, 'points', null) };
  var list = new ActionList(), used = {};
  for (var key in CURVE_CH) {
    if (!chans[key]) continue;
    var pts = normPoints(chans[key]);
    var cd = new ActionDescriptor(); var cr = new ActionReference();
    cr.putEnumerated(cTID('Chnl'), cTID('Chnl'), cTID(CURVE_CH[key]));
    cd.putReference(cTID('Chnl'), cr);
    var pl = new ActionList();
    for (var i = 0; i < pts.length; i++) {
      var pd = new ActionDescriptor(); pd.putDouble(cTID('Hrzn'), pts[i][0]); pd.putDouble(cTID('Vrtc'), pts[i][1]);
      pl.putObject(cTID('Pnt '), pd);
    }
    cd.putList(cTID('Crv '), pl);
    list.putObject(cTID('CrvA'), cd);
    used[key] = pts;
  }
  if (!list.count) fail('BAD_ARG', '需要 points 或 channels');
  var adj = new ActionDescriptor();
  adj.putEnumerated(sTID('presetKind'), sTID('presetKindType'), sTID('presetKindCustom'));
  adj.putList(cTID('Adjs'), list);
  var info = adjustmentFlow(doc, args, 'adj_curves', function () { return makeAdjustmentLayer(cTID('Crvs'), adj); });
  info.curves = used;
  return info;
}
