// _lib.jsx —— ps-repair 配方公共函数（scripts/psrun.py 会把它拼在配方正文前面）
//
// 配方写法：定义 function run(args) { ... return {数据}; }，出错直接 throw。
// 运行期全局（psrun.py 注入）：__ARGS__ 参数对象、__RESULT_PATH__ 结果文件、__RECIPE__ 配方名。
// ExtendScript 只支持 ES3：不要用 let/const/箭头函数/Array.indexOf/JSON/String.trim。
// 本地化：中文界面下图层、历史记录默认名都是中文，一律用 stringID/charID，不匹配本地化名字。

var FIX_PREFIX = '修_';            // “修_”：本工具产出的图层前缀
var TRIAL_PREFIX = '试做_';    // “试做_”：本工具产出的试做文档前缀
var __TARGET_DOC = null;

function sTID(s) { return stringIDToTypeID(s); }
function cTID(s) { return charIDToTypeID(s); }
function px(v) { return new UnitValue(Number(v), 'px'); }
function num(v) { return (v !== null && typeof v == 'object' && typeof v.as == 'function') ? v.as('px') : Number(v); }
function opt(args, key, dflt) { return (args && args[key] !== undefined && args[key] !== null) ? args[key] : dflt; }
function fail(code, msg) { throw new Error(code + ': ' + msg); }
function enumName(v) { var s = String(v); var i = s.lastIndexOf('.'); return (i >= 0 ? s.substr(i + 1) : s).toLowerCase(); }
function round2(v) { return Math.round(Number(v) * 100) / 100; }
function inList(v, arr) { for (var i = 0; i < arr.length; i++) if (arr[i] === v) return true; return false; }

// ---------- JSON（ES3 手写；非 ASCII 一律转 \uXXXX，结果文件是纯 ASCII） ----------
function __q(s) {
  s = String(s);
  var out = '"';
  for (var i = 0; i < s.length; i++) {
    var ch = s.charAt(i), c = s.charCodeAt(i);
    if (ch == '"') out += '\\"';
    else if (ch == '\\') out += '\\\\';
    else if (c < 0x20 || c > 0x7e) { var h = c.toString(16); while (h.length < 4) h = '0' + h; out += '\\u' + h; }
    else out += ch;
  }
  return out + '"';
}
function __json(v) {
  if (v === null || v === undefined) return 'null';
  var t = typeof v;
  if (t == 'number') return isFinite(v) ? String(v) : 'null';
  if (t == 'boolean') return v ? 'true' : 'false';
  if (t == 'string') return __q(v);
  if (t == 'function') return 'null';
  if (v instanceof UnitValue) return String(v.as('px'));
  if (v instanceof Array) {
    var a = [];
    for (var i = 0; i < v.length; i++) a.push(__json(v[i]));
    return '[' + a.join(',') + ']';
  }
  if (t == 'object') {
    var parts = [];
    for (var k in v) if (v.hasOwnProperty(k) && typeof v[k] != 'function') parts.push(__q(k) + ':' + __json(v[k]));
    return '{' + parts.join(',') + '}';
  }
  return __q(String(v));
}

// ---------- 文档 ----------
function findDoc(id) {
  for (var i = 0; i < app.documents.length; i++) if (app.documents[i].id == id) return app.documents[i];
  return null;
}
// 取目标文档并设为当前：args.doc_id 优先，否则当前文档。
function getDoc(args) {
  if (!app.documents.length) fail('NO_DOCUMENT', 'Photoshop 没有打开的文档');
  var doc;
  if (args && args.doc_id !== undefined && args.doc_id !== null) {
    doc = findDoc(args.doc_id);
    if (!doc) fail('DOC_NOT_FOUND', 'doc_id=' + args.doc_id);
  } else {
    doc = app.activeDocument;
  }
  if (app.activeDocument.id != doc.id) app.activeDocument = doc;
  __TARGET_DOC = doc;
  return doc;
}
function isTrialDoc(doc) { return doc.name.indexOf(TRIAL_PREFIX) == 0; }
function docInfo(doc) {
  var o = { id: doc.id, name: doc.name, width: num(doc.width), height: num(doc.height),
            resolution: doc.resolution, mode: enumName(doc.mode), bits: enumName(doc.bitsPerChannel),
            trial: isTrialDoc(doc) };
  try { o.profile = doc.colorProfileName; } catch (e) { o.profile = null; }
  try { o.path = doc.fullName.fsName; } catch (e2) { o.path = null; }
  return o;
}

// ---------- 图层 ----------
function walkLayers(container, fn, depth) {
  for (var i = 0; i < container.layers.length; i++) {
    var l = container.layers[i];
    if (fn(l, depth || 0) === true) return l;
    if (l.typename == 'LayerSet') { var r = walkLayers(l, fn, (depth || 0) + 1); if (r) return r; }
  }
  return null;
}
function findLayer(doc, id) {
  var hit = walkLayers(doc, function (l) { return l.id == id; });
  if (!hit) fail('LAYER_NOT_FOUND', 'layer_id=' + id);
  return hit;
}
// args.layer_id 指定的图层，否则当前图层。
function sourceLayer(doc, args) {
  return (args && args.layer_id !== undefined && args.layer_id !== null) ? findLayer(doc, args.layer_id) : doc.activeLayer;
}
function layerDescById(id) {
  var r = new ActionReference(); r.putIdentifier(sTID('layer'), id);
  return executeActionGet(r);
}
function maskState(id) {
  var d = layerDescById(id), o = { has_mask: false };
  if (d.hasKey(sTID('hasUserMask')) && d.getBoolean(sTID('hasUserMask'))) {
    o.has_mask = true;
    if (d.hasKey(sTID('userMaskEnabled'))) o.enabled = d.getBoolean(sTID('userMaskEnabled'));
    // 读回的浓度是 0-255（实测：设 50% 读回 128），换算成百分比
    if (d.hasKey(sTID('userMaskDensity'))) o.density = Math.round(d.getUnitDoubleValue(sTID('userMaskDensity')) * 100 / 255);
    if (d.hasKey(sTID('userMaskFeather'))) o.feather = round2(d.getUnitDoubleValue(sTID('userMaskFeather')));
  }
  return o;
}
function layerInfo(l) {
  var b = l.bounds;
  var o = { id: l.id, name: l.name, typename: l.typename, visible: l.visible,
            opacity: round2(l.opacity), blend: enumName(l.blendMode),
            bounds: [num(b[0]), num(b[1]), num(b[2]), num(b[3])] };
  if (l.typename == 'ArtLayer') { o.kind = enumName(l.kind); o.is_background = l.isBackgroundLayer; }
  try { var m = maskState(l.id); o.has_mask = m.has_mask; if (m.has_mask) o.mask = m; } catch (e) { o.has_mask = false; }
  return o;
}
function fixName(recipe, label) { return FIX_PREFIX + recipe + (label ? '_' + label : ''); }
// 保护用户原有图层：只允许改本工具产出的“修_”图层，除非显式 allow_any_layer。
function assertOwnLayer(layer, args) {
  if (layer.name.indexOf(FIX_PREFIX) != 0 && !opt(args, 'allow_any_layer', false))
    fail('PROTECTED_LAYER', '图层「' + layer.name + '」不是本工具产出的“修_”图层；确需修改请传 allow_any_layer:true');
}

// ---------- 选区 ----------
var SEL_TYPES = { replace: 'REPLACE', add: 'EXTEND', subtract: 'DIMINISH', intersect: 'INTERSECT' };
function selType(mode) {
  var k = SEL_TYPES[mode || 'replace'];
  if (!k) fail('BAD_ARG', 'mode 只能是 replace/add/subtract/intersect，收到 ' + mode);
  return SelectionType[k];
}
function selBounds(doc) {
  try { var b = doc.selection.bounds; return [num(b[0]), num(b[1]), num(b[2]), num(b[3])]; }
  catch (e) { return null; }
}
function hasSelection(doc) { return selBounds(doc) !== null; }
function findChannel(doc, name) {
  for (var i = 0; i < doc.channels.length; i++) if (doc.channels[i].name == name) return doc.channels[i];
  return null;
}
function rectPoints(r) {
  if (!(r instanceof Array) || r.length != 4) fail('BAD_ARG', 'rect 需要 [left,top,right,bottom]');
  var l = Number(r[0]), t = Number(r[1]), rr = Number(r[2]), b = Number(r[3]);
  if (!(rr > l && b > t)) fail('BAD_ARG', 'rect 需要 right>left 且 bottom>top：' + r);
  return [[l, t], [rr, t], [rr, b], [l, b]];
}
// 选区输入统一格式：{"rect":[l,t,r,b]} | {"polygon":[[x,y],...]} | {"channel":"名"} | "current" | "all" | "none"
// 缺省（undefined/null）= 沿用当前选区（没有也行）。返回“执行后是否有选区”。
function applySelection(doc, spec, mode) {
  if (spec === undefined || spec === null) return hasSelection(doc);
  if (spec === 'current') {
    if (!hasSelection(doc)) fail('NO_SELECTION', '要求使用当前选区，但文档没有选区');
    return true;
  }
  if (spec === 'none') { doc.selection.deselect(); return false; }
  if (spec === 'all') { doc.selection.selectAll(); return true; }
  var st = selType(mode);
  if (spec.rect) {
    doc.selection.select(rectPoints(spec.rect), st, 0, false);
  } else if (spec.polygon) {
    if (!(spec.polygon instanceof Array) || spec.polygon.length < 3) fail('BAD_ARG', 'polygon 至少 3 个点');
    doc.selection.select(spec.polygon, st, 0, true);
  } else if (spec.channel) {
    var ch = findChannel(doc, spec.channel);
    if (!ch) fail('CHANNEL_NOT_FOUND', '没有名为「' + spec.channel + '」的通道');
    doc.selection.load(ch, st, false);
  } else {
    fail('BAD_ARG', '选区格式应为 {"rect":[...]} / {"polygon":[...]} / {"channel":"名"} / "current"');
  }
  if (!hasSelection(doc)) fail('EMPTY_SELECTION', '选区为空');
  return true;
}

// ---------- 非破坏：工作图层 + 蒙版 ----------
// 盖印可见图层（新图层放在最顶层）。
function stampVisible(doc) {
  doc.activeLayer = doc.layers[0];
  var d = new ActionDescriptor(); d.putBoolean(sTID('duplicate'), true);
  executeAction(sTID('mergeVisible'), d, DialogModes.NO);
  return doc.activeLayer;
}
// 复制源图层（args.source="merged" 时改为盖印可见），命名为 修_<配方>_<标签>，设为当前图层。
function makeWorkLayer(doc, args, recipe) {
  var work;
  if (opt(args, 'source', 'layer') == 'merged') {
    work = stampVisible(doc);
  } else {
    var src = sourceLayer(doc, args);
    if (src.typename != 'ArtLayer' || src.kind != LayerKind.NORMAL)
      fail('SOURCE_NOT_PIXEL_LAYER', '源图层「' + src.name + '」不是普通像素图层；可改传 source:"merged"');
    work = src.duplicate();
    doc.activeLayer = work;
  }
  work.name = fixName(recipe, opt(args, 'label', ''));
  return work;
}
// 给当前图层建蒙版。how: RvlS 显示选区 / RvlA 全显 / HdSl 隐藏选区 / HdAl 全隐
function makeMask(how) {
  var d = new ActionDescriptor();
  d.putClass(cTID('Nw  '), cTID('Chnl'));
  var r = new ActionReference(); r.putEnumerated(cTID('Chnl'), cTID('Chnl'), cTID('Msk '));
  d.putReference(cTID('At  '), r);
  d.putEnumerated(cTID('Usng'), cTID('UsrM'), cTID(how));
  executeAction(cTID('Mk  '), d, DialogModes.NO);
}
function expandSelection(doc, n) { if (Number(n) > 0) doc.selection.expand(px(n)); }
// 给图层加蒙版：有选区→外扩 expand_px 后只露选区；无选区→全显蒙版。
function maskFromSelection(doc, layer, hadSel, expandPx) {
  doc.activeLayer = layer;
  if (hadSel) { expandSelection(doc, expandPx); makeMask('RvlS'); } else makeMask('RvlA');
}
// 设蒙版属性（非破坏，可随时再改）：feather 像素 / density 0-100 / enabled 布尔
// 实测（27.10.0）：一次 set 里放多个属性只生效一个，所以逐个属性单独 set。
function setMaskProps(layerId, p) {
  function setOne(fill) {
    var l = new ActionDescriptor(); fill(l);
    var r = new ActionReference(); r.putIdentifier(sTID('layer'), layerId);
    var d = new ActionDescriptor(); d.putReference(sTID('null'), r);
    d.putObject(sTID('to'), sTID('layer'), l);
    executeAction(sTID('set'), d, DialogModes.NO);
  }
  if (p.feather !== undefined && p.feather !== null)
    setOne(function (l) { l.putUnitDouble(sTID('userMaskFeather'), sTID('pixelsUnit'), Number(p.feather)); });
  if (p.density !== undefined && p.density !== null)
    setOne(function (l) { l.putUnitDouble(sTID('userMaskDensity'), sTID('percentUnit'), Number(p.density)); });
  if (p.enabled !== undefined && p.enabled !== null)
    setOne(function (l) { l.putBoolean(sTID('userMaskEnabled'), !!p.enabled); });
}
// 像素类配方收尾：可选蒙版羽化、取消选区、返回图层信息。
function finishLayer(doc, layer, args) {
  var f = opt(args, 'feather_px', 0);
  if (Number(f) > 0) setMaskProps(layer.id, { feather: f });
  doc.selection.deselect();
  doc.activeLayer = layer;
  return layerInfo(layer);
}
// 删除本次配方自己建的半成品图层（只删“修_”前缀的，出错时调用）。
function discardLayer(layer) {
  try { if (layer && layer.name.indexOf(FIX_PREFIX) == 0) layer.remove(); } catch (e) {}
}
// 把编辑目标切回图层像素（新建蒙版后 PS 会把编辑目标切到蒙版，滤镜会误作用在蒙版上）。
function targetPixels(doc) {
  var key = { rgb: 'RGB ', cmyk: 'CMYK', lab: 'Lab ', grayscale: 'Blck' }[enumName(doc.mode)] || 'RGB ';
  var d = new ActionDescriptor(); var r = new ActionReference();
  r.putEnumerated(cTID('Chnl'), cTID('Chnl'), cTID(key));
  d.putReference(cTID('null'), r); d.putBoolean(cTID('MkVs'), false);
  executeAction(cTID('slct'), d, DialogModes.NO);
}
// 选区暂存到临时 Alpha 通道（滤镜要在更大的矩形里算，算完再取回选区建蒙版）。
var TMP_CHANNEL = '__psrepair_tmp_sel';
function stashSelection(doc) {
  var old = findChannel(doc, TMP_CHANNEL); if (old) old.remove();
  var d = new ActionDescriptor(); var r = new ActionReference();
  r.putProperty(cTID('Chnl'), cTID('fsel')); d.putReference(cTID('null'), r);
  d.putString(cTID('Nm  '), TMP_CHANNEL);
  executeAction(cTID('Dplc'), d, DialogModes.NO);
}
function unstashSelection(doc) {
  var ch = findChannel(doc, TMP_CHANNEL);
  if (!ch) fail('INTERNAL', '临时选区通道丢失');
  doc.selection.load(ch, SelectionType.REPLACE, false);
}
function dropStash(doc) { try { var ch = findChannel(doc, TMP_CHANNEL); if (ch) ch.remove(); } catch (e) {} }
// 滤镜类公共流程（顺序：复制层 → 滤镜 → 建蒙版）：
// 选区（外扩 expand_px）暂存 → 复制源图层 → 显式选中 RGB 复合通道 → 在“选区外接框 + margin”矩形内
// 跑滤镜（整层跑太慢；矩形外被蒙版挡住）→ 取回选区建“显示选区”蒙版（无选区=全显）→ 可选羽化。
function filterFlow(doc, args, recipe, margin, applyFn) {
  var hadSel = applySelection(doc, opt(args, 'selection', null));
  var mb = null, rect = null, work = null;
  if (hadSel) { expandSelection(doc, opt(args, 'expand_px', 0)); mb = selBounds(doc); stashSelection(doc); }
  try {
    work = makeWorkLayer(doc, args, recipe);
    targetPixels(doc);
    doc.selection.deselect();
    if (mb) {
      var m = Math.ceil(Number(margin) + 2 * Number(opt(args, 'feather_px', 0)) + 4);
      rect = [Math.max(0, mb[0] - m), Math.max(0, mb[1] - m), Math.min(num(doc.width), mb[2] + m), Math.min(num(doc.height), mb[3] + m)];
      doc.selection.select(rectPoints(rect), SelectionType.REPLACE, 0, false);
    }
    applyFn(work);
    doc.activeLayer = work;
    if (hadSel) { unstashSelection(doc); makeMask('RvlS'); } else { doc.selection.deselect(); makeMask('RvlA'); }
  } catch (e) {
    discardLayer(work);  // 失败不留半成品图层
    throw e;
  } finally {
    if (hadSel) dropStash(doc);
  }
  var info = finishLayer(doc, work, args);
  info.used_selection = hadSel;
  info.filter_rect = rect;
  return info;
}

// ---------- 调整层 / 填充层 ----------
// 在当前图层上方建调整层；有选区时 PS 自动用选区做蒙版。typeKey 为调整类型 ID，adj 为其描述符。
function makeAdjustmentLayer(typeKey, adj) {
  var d = new ActionDescriptor(); var r = new ActionReference(); r.putClass(cTID('AdjL'));
  d.putReference(cTID('null'), r);
  var l = new ActionDescriptor(); l.putObject(cTID('Type'), typeKey, adj);
  d.putObject(cTID('Usng'), cTID('AdjL'), l);
  executeAction(cTID('Mk  '), d, DialogModes.NO);
  return app.activeDocument.activeLayer;
}
function makeFillLayer(typeKey, content) {
  var d = new ActionDescriptor(); var r = new ActionReference(); r.putClass(sTID('contentLayer'));
  d.putReference(cTID('null'), r);
  var l = new ActionDescriptor(); l.putObject(cTID('Type'), typeKey, content);
  d.putObject(cTID('Usng'), sTID('contentLayer'), l);
  executeAction(cTID('Mk  '), d, DialogModes.NO);
  return app.activeDocument.activeLayer;
}
// 调整/填充层公共流程：定插入位置 → 选区（外扩）→ 建层 → 命名 → 可选剪贴/羽化 → 取消选区。
function adjustmentFlow(doc, args, recipe, builder) {
  if (args.layer_id !== undefined && args.layer_id !== null) doc.activeLayer = findLayer(doc, args.layer_id);
  var hadSel = applySelection(doc, opt(args, 'selection', null));
  if (hadSel) expandSelection(doc, opt(args, 'expand_px', 0));
  var layer = builder();
  layer.name = fixName(recipe, opt(args, 'label', ''));
  if (opt(args, 'clip', false)) layer.grouped = true;
  if (!layerHasMaskSafe(layer)) makeMask(hadSel ? 'RvlS' : 'RvlA');
  var info = finishLayer(doc, layer, args);
  info.used_selection = hadSel;
  return info;
}
function layerHasMaskSafe(layer) { try { return maskState(layer.id).has_mask; } catch (e) { return false; } }
function rgbDesc(rgb) {
  if (!(rgb instanceof Array) || rgb.length != 3) fail('BAD_ARG', 'rgb 需要 [r,g,b]（0-255）');
  var c = new ActionDescriptor();
  c.putDouble(cTID('Rd  '), Number(rgb[0])); c.putDouble(cTID('Grn '), Number(rgb[1])); c.putDouble(cTID('Bl  '), Number(rgb[2]));
  return c;
}
function rgbToLab(rgb) {
  var c = new SolidColor(); c.rgb.red = rgb[0]; c.rgb.green = rgb[1]; c.rgb.blue = rgb[2];
  return [c.lab.l, c.lab.a, c.lab.b];
}
var BLEND_MODES = { normal: 'NORMAL', dissolve: 'DISSOLVE', darken: 'DARKEN', multiply: 'MULTIPLY', color_burn: 'COLORBURN',
  linear_burn: 'LINEARBURN', darker_color: 'DARKERCOLOR', lighten: 'LIGHTEN', screen: 'SCREEN', color_dodge: 'COLORDODGE',
  linear_dodge: 'LINEARDODGE', lighter_color: 'LIGHTERCOLOR', overlay: 'OVERLAY', soft_light: 'SOFTLIGHT',
  hard_light: 'HARDLIGHT', vivid_light: 'VIVIDLIGHT', linear_light: 'LINEARLIGHT', pin_light: 'PINLIGHT',
  hard_mix: 'HARDMIX', difference: 'DIFFERENCE', exclusion: 'EXCLUSION', subtract: 'SUBTRACT', divide: 'DIVIDE',
  hue: 'HUE', saturation: 'SATURATION', color: 'COLORBLEND', luminosity: 'LUMINOSITY' };
function blendMode(name) {
  var k = BLEND_MODES[name];
  if (!k) fail('BAD_ARG', '未知混合模式 ' + name);
  return BlendMode[k];
}

// ---------- 结果 ----------
function __historyTail(n) {
  var doc = null;
  try { if (__TARGET_DOC) { var probe = __TARGET_DOC.name; doc = __TARGET_DOC; } } catch (e) { doc = null; }
  if (!doc) { try { doc = app.activeDocument; } catch (e2) { return []; } }
  var out = [];
  try {
    var hs = doc.historyStates;
    for (var i = Math.max(0, hs.length - n); i < hs.length; i++) out.push(hs[i].name);
  } catch (e3) {}
  return out;
}
function __writeResult(s) {
  if (!__RESULT_PATH__) return;
  var part = new File(__RESULT_PATH__ + '.part');
  part.encoding = 'UTF-8'; part.lineFeed = 'Unix';
  if (!part.open('w')) return;
  part.write(s); part.close();
  var dst = new File(__RESULT_PATH__);
  if (dst.exists) dst.remove();
  part.rename(dst.name);
}
function __main() {
  var t0 = new Date().getTime();
  var res = { ok: false, recipe: __RECIPE__, data: null, error: null, elapsed_ms: 0, history: [] };
  var oldUnits = null, oldDialogs = null;
  try {
    oldUnits = app.preferences.rulerUnits; oldDialogs = app.displayDialogs;
    app.preferences.rulerUnits = Units.PIXELS;
    app.displayDialogs = DialogModes.NO;
    var data = run(__ARGS__ || {});
    res.data = (data === undefined) ? {} : data;
    res.ok = true;
  } catch (e) {
    res.error = String(e) + (e && e.line ? ' @line ' + e.line : '');
  }
  try { if (oldUnits !== null) app.preferences.rulerUnits = oldUnits; } catch (e2) {}
  try { if (oldDialogs !== null) app.displayDialogs = oldDialogs; } catch (e3) {}
  res.history = __historyTail(3);
  res.elapsed_ms = new Date().getTime() - t0;
  var s = __json(res);
  try { __writeResult(s); } catch (e4) {}
  return s;
}
