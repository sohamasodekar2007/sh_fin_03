"use client";

import Sidebar from "@/components/dashboard/Sidebar";
import ChatWindow from "@/components/chat/ChatWindow";

export default function ChatPage() {
  return (
    <main className="min-h-screen bg-bg flex">
      <Sidebar />
      <div className="flex-1 min-w-0">
        <ChatWindow />
      </div>
    </main>
  );
}
