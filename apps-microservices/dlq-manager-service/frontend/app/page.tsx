"use client"

import * as React from "react";
import { useState } from "react"
import Sidebar from "@/components/dlq/Sidebar"
import Dashboard from "@/components/dlq/Dashboard"
import SearchPage from "@/components/dlq/SearchPage"
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar"

type Page = "dashboard" | "search"

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("dashboard")

  return (
    <SidebarProvider>
      <Sidebar currentPage={currentPage} onPageChange={setCurrentPage} />
      <SidebarInset className="flex flex-col h-screen overflow-hidden bg-white-light w-full min-w-0">
        <header className="h-16 shrink-0 border-b border-gris-blanc bg-white-primary flex items-center px-4 md:px-8 gap-4">
          <SidebarTrigger />
          <h1 className="text-xl font-semibold text-noir-primary truncate">
            {currentPage === "dashboard" ? "Dashboard" : "Search & Re-queue"}
          </h1>
        </header>
        <main className="flex-1 overflow-auto">
            {currentPage === "dashboard" ? <Dashboard /> : <SearchPage />}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}