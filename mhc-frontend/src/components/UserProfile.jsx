// src/components/UserProfile.jsx
import { useState, useRef, useEffect } from "react";
import { useAuth } from "../useAuth";
import { startNewSession } from "../api";

export default function UserProfile({ onNewSession }) {
  const { user, logout } = useAuth();
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  if (!user) return null;

  const handleLogout = () => {
    setShowDropdown(false);
    logout();
  };

  const handleNewConversation = () => {
    const newSessionId = startNewSession();
    setShowDropdown(false);
    if (onNewSession) {
      onNewSession(newSessionId);
    }
    // Optional: Show confirmation
    console.log('Started new conversation session:', newSessionId);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className="flex items-center gap-2 rounded-full p-1 hover:bg-slate-100 transition"
      >
        <img
          src={user.picture}
          alt={user.name}
          className="h-8 w-8 rounded-full border border-slate-200"
        />
        <span className="text-sm text-slate-700 hidden sm:block">{user.name}</span>
      </button>

      {showDropdown && (
        <div className="absolute right-0 top-full mt-2 w-48 rounded-lg border border-slate-200 bg-white shadow-lg z-10">
          <div className="p-3 border-b border-slate-100">
            <p className="text-sm font-medium text-slate-800 truncate">{user.name}</p>
            <p className="text-xs text-slate-500 truncate mt-1">{user.email}</p>
          </div>
          <div className="p-1 space-y-1">
            <button
              onClick={handleNewConversation}
              className="w-full text-left px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-md"
            >
              New Conversation
            </button>
            <button
              onClick={handleLogout}
              className="w-full text-left px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-md"
            >
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}