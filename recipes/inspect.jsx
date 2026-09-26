// 配方：inspect
// 用途：只读查看 PS 状态：打开的文档、目标文档的图层树（id/名称/类型/蒙版/边界）、Alpha 通道、选区、最近历史。
// 参数：
//   doc_id       int   默认=当前文档   要看的文档；看完恢复原来的当前文档
//   max_layers   int   默认=300        图层条数上限（超出时 truncated=true）
// 产出：无（只读，不改文档；若指定了非当前文档会临时切换再切回）
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；没有打开的文档时返回 documents=[]、document=null。

function run(args) {
  var out = { app: app.version, documents: [], document: null };
  if (!app.documents.length) return out;
  var prev = app.activeDocument;
  for (var i = 0; i < app.documents.length; i++) {
    var d = app.documents[i], di = docInfo(d);
    di.active = (d.id == prev.id);
    out.documents.push(di);
  }
  var doc = getDoc(args);
  var max = opt(args, 'max_layers', 300), layers = [], count = 0;
  walkLayers(doc, function (l, depth) {
    count++;
    if (layers.length < max) { var li = layerInfo(l); li.depth = depth; layers.push(li); }
    return false;
  });
  var channels = [];
  for (var c = 0; c < doc.channels.length; c++) {
    var ch = doc.channels[c];
    if (ch.kind != ChannelType.COMPONENT) channels.push({ name: ch.name, kind: enumName(ch.kind) });
  }
  var hist = [];
  try { var hs = doc.historyStates; for (var h = Math.max(0, hs.length - 8); h < hs.length; h++) hist.push(hs[h].name); } catch (e) {}
  var info = docInfo(doc);
  info.active_layer_id = doc.activeLayer ? doc.activeLayer.id : null;
  info.layer_count = count;
  info.truncated = count > layers.length;
  info.layers = layers;
  info.alpha_channels = channels;
  info.selection = selBounds(doc);
  info.history_tail = hist;
  out.document = info;
  if (prev.id != doc.id) app.activeDocument = prev;
  return out;
}
