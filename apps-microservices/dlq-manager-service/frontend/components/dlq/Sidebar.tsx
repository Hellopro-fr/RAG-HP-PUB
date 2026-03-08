"use client"

import * as React from "react";
import { LayoutDashboard, Search } from "lucide-react"
import {
  Sidebar as ShadcnSidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
} from "@/components/ui/sidebar"

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
    <ShadcnSidebar collapsible="icon" className="bg-white-primary border-r border-gris-blanc">
      <SidebarHeader className="h-16 border-b border-gris-blanc flex justify-center px-4">
        <div className="flex items-center gap-2 overflow-hidden h-full">
          <img src="https://www.hellopro.fr/hellopro_fr/images/hp-logo.svg" alt="Hellopro Logo" className="h-6 w-auto shrink-0" />
          <span className="font-semibold text-noir-primary truncate group-data-[collapsible=icon]:hidden">DLQ Manager</span>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const Icon = item.icon
                const isActive = currentPage === item.id
                return (
                  <SidebarMenuItem key={item.id}>
                    <SidebarMenuButton
                      tooltip={item.label}
                      isActive={isActive}
                      onClick={() => onPageChange(item.id as "dashboard" | "search")}
                      className={`transition-colors ${
                        isActive 
                          ? "bg-bleu-light text-bleu-primary hover:bg-bleu-light hover:text-bleu-primary" 
                          : "text-gris-primary hover:bg-clair-3 hover:text-noir-primary"
                      }`}
                      style={isActive ? { color: "var(--bleu-primary)", backgroundColor: "var(--bleu-light)" } : {}}
                    >
                      <Icon />
                      <span>{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </ShadcnSidebar>
  )
}