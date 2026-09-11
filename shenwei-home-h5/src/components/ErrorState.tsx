/** 错误态卡片：token 缺失/失效。不依赖 JSSDK，提供手动返回引导。 */
export function ErrorState({ title, message }: { title: string; message: string }) {
  return (
    <div className="app">
      <div className="state-card">
        <h3>{title}</h3>
        <p>{message}<br />如页面无法返回，请关闭当前页后从小程序重新进入。</p>
        <button onClick={() => {
          // JSSDK 可用时返回小程序；不可用时用户手动关闭
          const w = window as unknown as { wx?: { miniProgram?: { navigateBack: () => void } } };
          if (w.wx?.miniProgram) {
            w.wx.miniProgram.navigateBack();
          } else {
            alert('请点击右上角关闭本页面，返回小程序');
          }
        }}>返回小程序</button>
      </div>
    </div>
  );
}
