// 配方：place_image
// 用途：把外部图片（如即梦局部重绘的补丁）置入为嵌入智能对象，按左上角像素坐标对位，可指定尺寸。
// 参数：
//   doc_id      int      默认=当前文档
//   path        str      必填   图片路径（png/jpg/psd…）
//   x, y        number   必填   放置后图片左上角在文档里的像素坐标
//   width       number   可选   目标宽（像素）；只给宽或只给高时按原比例；都不给=原图像素尺寸（1:1）
//   height      number   可选   目标高（像素）
//   layer_id    int      默认=当前图层   新层插在它上方
//   selection   选区     默认=不用（蒙版全显）；显式给了才按选区建蒙版（{"rect"}/{"polygon"}/{"channel"}/"current"）
//   expand_px   int      默认=0
//   feather_px  number   默认=0
//   linked      bool     默认=false   true=置入链接的智能对象
//   label       str      默认=""
// 产出：图层「修_place_image_<label>」（智能对象 + 蒙版）；返回实际 bounds 与四角坐标 corners
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py：1:1 对位、按宽等比缩放、选区蒙版；大图 1:1 复原）；linked 未验证。
// 费用/限制：本地、不扣积分；PS“置入时调整图像大小”会先把大图缩进画布，本配方用智能对象原始尺寸
//   （smartObjectMore.size）还原成 1:1 或指定尺寸，再平移对位；非整数缩放会重采样。

function soCorners(layerId) {
  var som = layerDescById(layerId).getObjectValue(sTID('smartObjectMore'));
  var t = som.getList(sTID('transform'));  // 四角：左上、右上、右下、左下，各 x,y
  var sz = som.getObjectValue(sTID('size'));
  return { l: t.getDouble(0), t: t.getDouble(1), r: t.getDouble(4), b: t.getDouble(5),
           nw: sz.getDouble(sTID('width')), nh: sz.getDouble(sTID('height')) };
}

function run(args) {
  var doc = getDoc(args);
  var path = opt(args, 'path', '');
  var f = new File(path);
  if (!path || !f.exists) fail('FILE_NOT_FOUND', '找不到图片：' + path);
  var x = opt(args, 'x', null), y = opt(args, 'y', null);
  if (x === null || y === null) fail('BAD_ARG', 'x, y 必填（左上角，文档像素）');
  var w = opt(args, 'width', null), h = opt(args, 'height', null);
  if ((w !== null && !(w > 0)) || (h !== null && !(h > 0))) fail('BAD_ARG', 'width/height 必须 > 0');
  if (args.layer_id !== undefined && args.layer_id !== null) doc.activeLayer = findLayer(doc, args.layer_id);

  var d = new ActionDescriptor();
  d.putPath(cTID('null'), f);
  d.putEnumerated(cTID('FTcs'), cTID('QCSt'), cTID('Qcsa'));
  var o = new ActionDescriptor(); o.putUnitDouble(cTID('Hrzn'), cTID('#Pxl'), 0); o.putUnitDouble(cTID('Vrtc'), cTID('#Pxl'), 0);
  d.putObject(cTID('Ofst'), cTID('Ofst'), o);
  if (opt(args, 'linked', false)) d.putBoolean(cTID('Lnkd'), true);
  executeAction(cTID('Plc '), d, DialogModes.NO);
  var layer = doc.activeLayer;
  layer.name = fixName('place_image', opt(args, 'label', ''));

  var c = soCorners(layer.id);
  var tw = (w !== null) ? Number(w) : (h !== null ? Number(h) * c.nw / c.nh : c.nw);
  var th = (h !== null) ? Number(h) : (w !== null ? Number(w) * c.nh / c.nw : c.nh);
  var sx = tw / (c.r - c.l) * 100, sy = th / (c.b - c.t) * 100;
  if (Math.abs(sx - 100) > 1e-6 || Math.abs(sy - 100) > 1e-6) layer.resize(sx, sy, AnchorPosition.TOPLEFT);
  c = soCorners(layer.id);
  var dx = Number(x) - c.l, dy = Number(y) - c.t;
  if (Math.abs(dx) > 1e-6 || Math.abs(dy) > 1e-6) layer.translate(px(dx), px(dy));

  var spec = opt(args, 'selection', null);
  var hadSel = (spec === null) ? false : applySelection(doc, spec);
  if (spec === null) doc.selection.deselect();
  maskFromSelection(doc, layer, hadSel, opt(args, 'expand_px', 0));
  var info = finishLayer(doc, layer, args);
  c = soCorners(layer.id);
  info.corners = [round2(c.l), round2(c.t), round2(c.r), round2(c.b)];
  info.native_size = [c.nw, c.nh];
  info.used_selection = hadSel;
  return info;
}
