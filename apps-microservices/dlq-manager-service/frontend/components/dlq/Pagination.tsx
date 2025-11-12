"use client"

import * as React from "react";
import { useState } from "react";
import { Button } from "@/components/ui/button"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Input } from "@/components/ui/input";

interface PaginationProps {
  currentPage: number
  totalItems: number
  itemsPerPage: number
  onPageChange: (page: number) => void
}

export default function Pagination({ currentPage, totalItems, itemsPerPage, onPageChange }: PaginationProps) {
  const totalPages = Math.ceil(totalItems / itemsPerPage)
  const hasPrevious = currentPage > 1
  const hasNext = currentPage < totalPages
  const [goToPage, setGoToPage] = useState(currentPage.toString());

  const handleGoToPage = (e: React.FormEvent) => {
    e.preventDefault();
    const pageNum = parseInt(goToPage, 10);
    if (!isNaN(pageNum) && pageNum >= 1 && pageNum <= totalPages) {
      onPageChange(pageNum);
    } else {
      alert(`Please enter a valid page number between 1 and ${totalPages}.`);
      setGoToPage(currentPage.toString());
    }
  };
  
  React.useEffect(() => {
    setGoToPage(currentPage.toString());
  }, [currentPage]);

  if (totalPages <= 1) {
      return null;
  }

  return (
    <div className="flex justify-center items-center gap-6">
      <Button
        variant="outline"
        disabled={!hasPrevious}
        onClick={() => onPageChange(currentPage - 1)}
        style={hasPrevious ? { borderColor: "var(--bleu-primary)", color: "var(--bleu-primary)" } : {}}
      >
        <ChevronLeft className="w-4 h-4 mr-2" />
        Previous
      </Button>

      <div className="text-sm text-gris-primary font-medium px-4 py-2 hidden sm:block">
        Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
      </div>

      <form onSubmit={handleGoToPage} className="flex items-center gap-2">
        <Input 
          type="number"
          min="1"
          max={totalPages}
          value={goToPage}
          onChange={(e) => setGoToPage(e.target.value)}
          className="w-16 h-9 text-center"
        />
        <Button type="submit" variant="outline" size="sm">Go</Button>
      </form>

      <Button
        variant="outline"
        disabled={!hasNext}
        onClick={() => onPageChange(currentPage + 1)}
        style={hasNext ? { borderColor: "var(--bleu-primary)", color: "var(--bleu-primary)" } : {}}
      >
        Next
        <ChevronRight className="w-4 h-4 ml-2" />
      </Button>
    </div>
  )
}