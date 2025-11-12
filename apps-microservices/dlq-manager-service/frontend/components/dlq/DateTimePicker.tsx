"use client"

import * as React from "react"
import { format } from "date-fns"
import { Calendar as CalendarIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Input } from "@/components/ui/input"

interface DateTimePickerProps {
  date: Date | undefined
  setDate: (date: Date | undefined) => void
}

export function DateTimePicker({ date, setDate }: DateTimePickerProps) {
  const handleDateSelect = (selectedDate: Date | undefined) => {
    if (!selectedDate) {
        setDate(undefined);
        return;
    };
    // If a date was already selected, preserve its time. Otherwise, default to midnight.
    const hours = date ? date.getHours() : 0;
    const minutes = date ? date.getMinutes() : 0;
    
    const newDate = new Date(selectedDate);
    newDate.setHours(hours);
    newDate.setMinutes(minutes);
    setDate(newDate);
  }

  const handleTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    const newDate = date ? new Date(date) : new Date();
    
    let numericValue = parseInt(value, 10);
    if (isNaN(numericValue)) return;

    if (name === "hours") {
      if (numericValue < 0 || numericValue > 23) return;
      newDate.setHours(numericValue);
    }
    if (name === "minutes") {
      if (numericValue < 0 || numericValue > 59) return;
      newDate.setMinutes(numericValue);
    }
    setDate(newDate);
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant={"outline"}
          className={cn(
            "w-full justify-start text-left font-normal",
            !date && "text-muted-foreground"
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4" />
          {date ? format(date, "dd/MM/yyyy HH:mm") : <span>Pick a date</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0">
        <Calendar
          mode="single"
          selected={date}
          onSelect={handleDateSelect}
          initialFocus
        />
        <div className="p-3 border-t border-border flex items-center justify-center gap-2">
            <Input
                type="number"
                name="hours"
                value={date ? date.getHours().toString().padStart(2, '0') : "00"}
                onChange={handleTimeChange}
                className="w-16 h-8 text-center"
                min="0"
                max="23"
            />
            <span>:</span>
            <Input
                type="number"
                name="minutes"
                value={date ? date.getMinutes().toString().padStart(2, '0') : "00"}
                onChange={handleTimeChange}
                className="w-16 h-8 text-center"
                min="0"
                max="59"
            />
        </div>
      </PopoverContent>
    </Popover>
  )
}