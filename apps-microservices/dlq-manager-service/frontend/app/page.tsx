"use client"

import { useState } from "react"
import Sidebar from "@/components/dlq/Sidebar"
import Dashboard from "@/components/dlq/Dashboard"
import SearchPage from "@/components/dlq/SearchPage"

type Page = "dashboard" | "search"

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("dashboard")

  return (
    <div className="flex h-screen bg-white-light">
      <Sidebar currentPage={currentPage} onPageChange={setCurrentPage} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="h-16 border-b border-gris-blanc bg-white-primary flex items-center px-8">
          <h1 className="text-xl font-semibold text-noir-primary">
            {currentPage === "dashboard" ? "Dashboard" : "Search & Re-queue"}
          </h1>
        </header>
        <main className="flex-1 overflow-auto">{currentPage === "dashboard" ? <Dashboard /> : <SearchPage />}</main>
      </div>
    </div>
  )
}
