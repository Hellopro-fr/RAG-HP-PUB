"use client"
import { Asterisk, MoreHorizontal, Menu, ChevronDown } from "lucide-react"
import { useState } from "react"
import GhostIconButton from "./GhostIconButton"
import { Slider } from "./ui/slider"

export default function Header({ createNewChat, sidebarCollapsed, setSidebarOpen, selectedBotName, setSelectedBotName, selectedBot, setSelectedBot, selectedProvider, setSelectedProvider, temperature, setTemperature }) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)

  const chatbots = [
    { name: "DeepSeek-V3.2-Exp", provider: 'deepseek', model_name: 'deepseek-chat', icon: <Asterisk className="h-4 w-4" /> },
    { name: "gpt-4.1-2025-04-14", provider: 'gpt', model_name: 'gpt-4.1-2025-04-14', icon: <Asterisk className="h-4 w-4" /> },
    { name: "gpt-4o-2024-08-06", provider: 'gpt', model_name: 'gpt-4o-2024-08-06', icon: <Asterisk className="h-4 w-4" /> },
    { name: "gpt-4o-2024-11-20", provider: 'gpt', model_name: 'gpt-4o-2024-11-20', icon: <Asterisk className="h-4 w-4" /> },
    // { name: "qwen/qwen3-coder", provider: 'openrouter', model_name: 'qwen/qwen3-coder', icon: <Asterisk className="h-4 w-4" /> },
  ]

  return (
    <div className="sticky top-0 z-30 flex items-center gap-2 border-b border-zinc-200/60 bg-white/80 px-4 py-3 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/70">
      {sidebarCollapsed && (
        <button
          onClick={() => setSidebarOpen(true)}
          className="md:hidden inline-flex items-center justify-center rounded-lg p-2 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-zinc-800"
          aria-label="Open sidebar"
        >
          <Menu className="h-5 w-5" />
        </button>
      )}

      <div className="hidden md:flex relative">
        <button
          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
          className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-3 py-2 text-sm font-semibold tracking-tight hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-800"
        >
          {typeof chatbots.find((bot) => bot.model_name === selectedBot)?.icon === "string" ? (
            <span className="text-sm">{chatbots.find((bot) => bot.model_name === selectedBot)?.icon}</span>
          ) : (
            chatbots.find((bot) => bot.model_name === selectedBot)?.icon
          )}
          {selectedBotName}
          <ChevronDown className="h-4 w-4" />
        </button>

        {isDropdownOpen && (
          <div className="absolute top-full left-0 mt-1 w-48 rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-800 dark:bg-zinc-950 z-50">
            {chatbots.map((bot) => (
              <button
                key={bot.name}
                onClick={() => {
                  setSelectedBot(bot.model_name)
                  setSelectedBotName(bot.name)
                  setIsDropdownOpen(false)
                  setSelectedProvider(bot.provider)
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-zinc-100 dark:hover:bg-zinc-800 first:rounded-t-lg last:rounded-b-lg"
              >
                {typeof bot.icon === "string" ? <span className="text-sm">{bot.icon}</span> : bot.icon}
                {bot.name}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 ml-4">
        <span className="text-sm font-medium">Temperature: {temperature.toFixed(1)}</span>
        <Slider
          value={[temperature]}
          max={1}
          min={0}
          step={0.1}
          className="w-[100px]"
          onValueChange={(value) => setTemperature(value[0])}
        />
      </div>

      <div className="ml-auto flex items-center gap-2">
        {/* <GhostIconButton label="More">
          <MoreHorizontal className="h-4 w-4" />
        </GhostIconButton> */}
      </div>
    </div>
  )
}
