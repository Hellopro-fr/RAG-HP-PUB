"use client"

import { LayoutDashboard, Search } from "lucide-react"

interface SidebarProps {
  currentPage: "dashboard" | "search"
  onPageChange: (page: "dashboard" | "search") => void
}

export default function Sidebar({ currentPage, onPageChange }: SidebarProps) {
  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "search", label: "Search & Re-queue", icon: Search },
  ] as const

  return (
    <aside className="w-64 bg-white-primary border-r border-gris-blanc flex flex-col">
      {/* Logo Area */}
      <div className="h-16 border-b border-gris-blanc flex items-center px-6">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg" style={{ backgroundColor: "var(--bleu-primary)" }} />
          <span className="font-semibold text-noir-primary">DLQ Manager</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-6 space-y-2">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = currentPage === item.id
          return (
            <button
              key={item.id}
              onClick={() => onPageChange(item.id as "dashboard" | "search")}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                isActive ? "bg-bleu-light text-bleu-primary" : "text-gris-primary hover:bg-clair-3"
              }`}
              style={isActive ? { color: "var(--bleu-primary)", backgroundColor: "var(--bleu-light)" } : {}}
            >
              <Icon className="w-5 h-5" />
              <span className="font-medium">{item.label}</span>
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
