import { BookSteamIcon, TrashIcon } from "./icons";

interface HeaderProps {
  kitchenStatus: "checking" | "online" | "offline";
  onClear: () => void;
  clearDisabled: boolean;
}

export default function Header({ kitchenStatus, onClear, clearDisabled }: HeaderProps) {
  return (
    <header className="plate">
      <div className="plate__inner">
        <div className="plate__mark">
          <BookSteamIcon className="plate__icon" />
          <div>
            <h1 className="plate__title">Ask My Cookbook</h1>
            <p className="plate__subtitle">Answers pulled from the cookbooks you file — nothing else.</p>
          </div>
        </div>
        <div className="plate__actions">
          <span className={`status status--${kitchenStatus}`} role="status">
            <span className="status__dot" aria-hidden="true" />
            {kitchenStatus === "checking" && "Checking the kitchen…"}
            {kitchenStatus === "online" && "Kitchen online"}
            {kitchenStatus === "offline" && "Kitchen unreachable"}
          </span>
          <button type="button" className="btn btn--ghost" onClick={onClear} disabled={clearDisabled}>
            <TrashIcon className="btn__icon" />
            Clear chat
          </button>
        </div>
      </div>
    </header>
  );
}
