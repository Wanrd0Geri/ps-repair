// 配方：adj_levels
// 用途：色阶调整层（带蒙版）：拉黑白场、调中间调 gamma、压输出范围（如给远景加一层灰雾：output_black 抬高）。
// 参数：
//   doc_id         int      默认=当前文档
//   input_black    int      默认=0      输入黑场 0-253
//   input_white    int      默认=255    输入白场 2-255
//   gamma          number   默认=1.0    0.1-9.99，>1 提亮中间调
//   output_black   int      默认=0
//   output_white   int      默认=255
//   channel        str      默认="rgb"  rgb/red/green/blue
//   selection      选区     默认=沿用当前选区；无选区=全图
//   layer_id / expand_px / feather_px / clip / label   同 adj_curves
// 产出：图层「修_adj_levels_<label>」（色阶调整层 + 选区蒙版）；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py；读回描述符 green 通道 input/gamma/output 与输入一致）
// 费用/限制：本地、不扣积分。

var LV_CH = { rgb: 'Cmps', red: 'Rd  ', green: 'Grn ', blue: 'Bl  ' };

function intPair(a, b) { var l = new ActionList(); l.putInteger(Math.round(a)); l.putInteger(Math.round(b)); return l; }

function run(args) {
  var doc = getDoc(args);
  var ch = LV_CH[opt(args, 'channel', 'rgb')];
  if (!ch) fail('BAD_ARG', 'channel 只能是 rgb/red/green/blue');
  var ib = Number(opt(args, 'input_black', 0)), iw = Number(opt(args, 'input_white', 255));
  var ob = Number(opt(args, 'output_black', 0)), ow = Number(opt(args, 'output_white', 255));
  var g = Number(opt(args, 'gamma', 1.0));
  if (!(iw - ib >= 2)) fail('BAD_ARG', 'input_white 要比 input_black 大至少 2');
  if (!(g >= 0.1 && g <= 9.99)) fail('BAD_ARG', 'gamma 范围 0.1-9.99');
  var la = new ActionDescriptor(); var r = new ActionReference();
  r.putEnumerated(cTID('Chnl'), cTID('Chnl'), cTID(ch));
  la.putReference(cTID('Chnl'), r);
  la.putList(cTID('Inpt'), intPair(ib, iw));
  la.putDouble(cTID('Gmm '), g);
  la.putList(cTID('Otpt'), intPair(ob, ow));
  var list = new ActionList(); list.putObject(cTID('LvlA'), la);
  var adj = new ActionDescriptor();
  adj.putEnumerated(sTID('presetKind'), sTID('presetKindType'), sTID('presetKindCustom'));
  adj.putList(cTID('Adjs'), list);
  var info = adjustmentFlow(doc, args, 'adj_levels', function () { return makeAdjustmentLayer(cTID('Lvls'), adj); });
  info.levels = { channel: opt(args, 'channel', 'rgb'), input: [ib, iw], gamma: g, output: [ob, ow] };
  return info;
}
