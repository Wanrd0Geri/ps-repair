// 配方：selection_save_channel
// 用途：把当前选区存成 Alpha 通道（以后用 {"channel":"名"} 或 selection_load_channel 取回），便于多步复用。
// 参数：
//   doc_id      int    默认=当前文档
//   name        str    必填   通道名（自己起，避免和 PS 默认名“Alpha 1”混淆）
//   overwrite   bool   默认=false   同名通道已存在时 true=覆盖，false=报错
// 产出：Alpha 通道（不改任何图层）；返回通道名与总数
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；通道会随 PSD 保存，PNG 导出不含通道。

function run(args) {
  var doc = getDoc(args);
  var name = opt(args, 'name', '');
  if (!name) fail('BAD_ARG', 'name 必填');
  if (!hasSelection(doc)) fail('NO_SELECTION', '没有选区可存');
  var existing = findChannel(doc, name);
  if (existing) {
    if (!opt(args, 'overwrite', false)) fail('CHANNEL_EXISTS', '已有通道「' + name + '」；覆盖请传 overwrite:true');
    doc.selection.store(existing, SelectionType.REPLACE);
  } else {
    // 等于“选择 > 存储选区 > 新建通道”，不会把编辑目标切到新通道
    var d = new ActionDescriptor(); var r = new ActionReference();
    r.putProperty(cTID('Chnl'), cTID('fsel'));
    d.putReference(cTID('null'), r);
    d.putString(cTID('Nm  '), name);
    executeAction(cTID('Dplc'), d, DialogModes.NO);
  }
  if (!findChannel(doc, name)) fail('SAVE_FAILED', '存储后找不到通道「' + name + '」');
  return { channel: name, overwritten: !!existing, bounds: selBounds(doc), channel_count: doc.channels.length };
}
