import { BookSteamIcon, MenuIcon, PlusIcon } from "./icons";

interface HeaderProps {
  kitchenStatus: "checking" | "online" | "offline";
  onNewChat: () => void;
  newChatDisabled: boolean;
  onToggleSidebar: () => void;
}

export default function Header({ kitchenStatus, onNewChat, newChatDisabled, onToggleSidebar }: HeaderProps) {
  return (
    <header className="plate">
      <div className="plate__inner">
        <button type="button" className="plate__menu" onClick={onToggleSidebar} aria-label="Show chats and cookbooks">
          <MenuIcon className="plate__menu-icon" />
        </button>
        <div className="plate__mark">
          <BookSteamIcon className="plate__icon" />
          <div>
            <h1 className="plate__title">Cookbook AI</h1>
            <p className="plate__subtitle">Your private recipe assistant</p>
          </div>
        </div>
        <div className="plate__actions">
          <span className={`status status--${kitchenStatus}`} role="status">
            <span className="status__dot" aria-hidden="true" />
            {kitchenStatus === "checking" && "Connecting"}
            {kitchenStatus === "online" && "Ready"}
            {kitchenStatus === "offline" && "Offline"}
          </span>
          <button type="button" className="btn btn--ghost" onClick={onNewChat} disabled={newChatDisabled}>
            <PlusIcon className="btn__icon" />
            New chat
          </button>
        </div>
      </div>
    </header>
  );
}
