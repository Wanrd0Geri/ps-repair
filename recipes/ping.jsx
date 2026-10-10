// 配方：ping
// 用途：探活：PS 能不能马上响应脚本（有弹窗或模态对话框、别的脚本在跑、暂存盘满时会卡住）。只读，不改任何东西。
// 参数：无
// 产出：无；返回 PS 版本、打开的文档数、当前文档（id/名/尺寸/模式/位深）。psrun 另附系统盘剩余空间（disk）
// 验证：2026-10-10 PS 27.10.0 Windows 实跑（tests/run_tests.py）
// 费用/限制：用 `psrun.py --ping` 调：COM/AppleEvent 等 15 秒，总共 30 秒。超时就是 PS 没响应，先看 PS 窗口有没有弹窗，
//   不要接着发写操作

function run(args) {
  var o = { version: app.version, documents: app.documents.length, active: null };
  if (app.documents.length) {
    try {
      var d = app.activeDocument;
      o.active = { id: d.id, name: d.name, width: num(d.width), height: num(d.height),
                   mode: enumName(d.mode), bits: enumName(d.bitsPerChannel) };
    } catch (e) {}
  }
  return o;
}
