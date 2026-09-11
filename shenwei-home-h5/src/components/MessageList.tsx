/** 消息流：user/assistant/system 三态 + 人工金标 + 图片/占位。 */
import type { MessageItem } from '../api';

export interface MsgVM extends MessageItem {
  picBroken?: boolean;
}

function Avatar({ isHuman }: { isHuman: boolean }) {
  return (
    <div className="avatar">
      {isHuman ? (
        <div className="human-mini" aria-label="人工客服" />
      ) : (
        <div className="bot-mini" aria-label="智能客服">
          <div className="bot-mini-visor">
            <div className="bot-mini-eye left" />
            <div className="bot-mini-eye right" />
            <div className="bot-mini-mouth" />
          </div>
        </div>
      )}
    </div>
  );
}

function MessageRow({ item, onPicError, onPicTap }: {
  item: MsgVM;
  onPicError: (id: string) => void;
  onPicTap: (url: string) => void;
}) {
  const isHuman = item.kind === 'boss_reply';

  if (item.role === 'system') {
    return (
      <div className="sys-tip" role="status">
        {item.content.content}
      </div>
    );
  }

  return (
    <div className={`msg ${item.role === 'user' ? 'user' : ''}`}>
      {item.role !== 'user' && <Avatar isHuman={isHuman} />}
      <div className={`bubble ${item.role === 'user' ? 'mine' : 'bot'} ${item.msg_type === 'image' ? 'pic-bubble' : ''}`}>
        {isHuman && <div className="human-corner-tag">人工</div>}
        {item.msg_type === 'image' ? (
          item.picBroken ? (
            <div className="pic-fallback" data-testid="pic-fallback">
              <div className="pic-fallback-icon">🖼</div>
              <div className="pic-fallback-text">图片加载失败</div>
            </div>
          ) : (
            <img
              className="pic"
              src={item.content.image_url}
              alt="图片消息"
              loading="lazy"
              onError={() => onPicError(item.id)}
              onClick={() => item.content.image_url && onPicTap(item.content.image_url)}
            />
          )
        ) : (
          <span>{item.content.content}</span>
        )}
        {item.status === 'failed' && <span className="fail-mark">!</span>}
      </div>
    </div>
  );
}

export function MessageList({ items, onPicError, onPicTap }: {
  items: MsgVM[];
  onPicError: (id: string) => void;
  onPicTap: (url: string) => void;
}) {
  return (
    <>
      {items.map((item) => (
        <MessageRow key={item.id} item={item} onPicError={onPicError} onPicTap={onPicTap} />
      ))}
    </>
  );
}
