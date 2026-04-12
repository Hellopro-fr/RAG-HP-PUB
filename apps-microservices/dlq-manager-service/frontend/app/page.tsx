"use client"

import * as React from "react";
import { useState } from "react"
import Sidebar from "@/components/dlq/Sidebar"
import Dashboard from "@/components/dlq/Dashboard"
import SearchPage from "@/components/dlq/SearchPage"
import RulesPage from "@/components/dlq/RulesPage"
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar"
import { AutoArchiveRule } from "@/lib/api"

type Page = "dashboard" | "search" | "rules"

export interface RuleCriteria {
  search_term?: string;
  filters?: Record<string, any>;
}

export default function App() {
  const[currentPage, setCurrentPage] = useState<Page>("dashboard")
  const [injectedRuleCriteria, setInjectedRuleCriteria] = useState<RuleCriteria | null>(null);

  const getPageTitle = () => {
    switch (currentPage) {
      case "dashboard": return "Dashboard";
      case "search": return "Search & Re-queue";
      case "rules": return "Auto-Archive Rules";
    }
  }

  const handleViewRuleMatches = (rule: AutoArchiveRule) => {
    setInjectedRuleCriteria({
      search_term: rule.search_term,
      filters: rule.filters,
    });
    setCurrentPage("search");
  };

  const handleClearInjectedCriteria = () => {
    setInjectedRuleCriteria(null);
  };

  return (
    <SidebarProvider>
      <Sidebar currentPage={currentPage} onPageChange={setCurrentPage} />
      <SidebarInset className="flex flex-col h-screen overflow-hidden bg-white-light w-full min-w-0">
        <header className="h-16 shrink-0 border-b border-gris-blanc bg-white-primary flex items-center px-4 md:px-8 gap-4">
          <SidebarTrigger />
          <h1 className="text-xl font-semibold text-noir-primary truncate">
            {getPageTitle()}
          </h1>
        </header>
        <main className="flex-1 overflow-auto">
            {currentPage === "dashboard" && <Dashboard />}
            {currentPage === "search" && (
              <SearchPage
                injectedCriteria={injectedRuleCriteria}
                onClearInjectedCriteria={handleClearInjectedCriteria}
              />
            )}
            {currentPage === "rules" && (
              <RulesPage onViewRuleMatches={handleViewRuleMatches} />
            )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}