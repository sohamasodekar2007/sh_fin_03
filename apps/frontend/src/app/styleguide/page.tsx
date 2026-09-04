"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Bar, BarChart, CartesianGrid, XAxis } from "recharts";
import { Home, Inbox, Settings, CalendarIcon as CalIcon } from "lucide-react";
import { toast } from "sonner";

import { Panel } from "@/components/cfo/Panel";
import { ThemeToggle } from "@/components/cfo/ThemeToggle";
import { KpiStrip, type Kpi } from "@/components/cfo/KpiStrip";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AspectRatio } from "@/components/ui/aspect-ratio";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from "@/components/ui/carousel";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Drawer, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle, DrawerTrigger, DrawerClose } from "@/components/ui/drawer";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Input } from "@/components/ui/input";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Label } from "@/components/ui/label";
import {
  Menubar,
  MenubarContent,
  MenubarItem,
  MenubarMenu,
  MenubarTrigger,
} from "@/components/ui/menubar";
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuTrigger,
} from "@/components/ui/navigation-menu";
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from "@/components/ui/pagination";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Toggle } from "@/components/ui/toggle";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

// ---------------------------------------------------------------------------
// Dummy data — this page exists only to visually diff against the template
// running on Vite (see "How to test" in the Phase 8 prompt). None of this
// is real CloudCare data; that starts in a later phase.
// ---------------------------------------------------------------------------

const DUMMY_KPIS: Kpi[] = [
  { label: "Monthly spend", value: 48210, fmt: "usdCompact", delta: -4.2, deltaLabel: "vs last month", hint: "Total billed cost across every connected account this month." },
  { label: "Wasted spend", value: 0.186, fmt: "pct", delta: 2.1, deltaLabel: "vs last month", tone: "ember", hint: "Share of spend attributable to idle or over-provisioned resources." },
  { label: "Savings identified", value: 8960, fmt: "usdCompact", delta: 12.4, deltaLabel: "vs last month", tone: "mint", hint: "Sum of expected_monthly_savings across open proposals." },
  { label: "Open proposals", value: 14, fmt: "usd", delta: null, deltaLabel: "pending review", hint: "Proposals awaiting human approval." },
  { label: "Avg. confidence", value: 0.82, fmt: "pct", delta: 3.5, deltaLabel: "vs last month", hint: "Mean confidence_score across proposals from the last Supervisor run." },
];

const DUMMY_CHART_DATA = [
  { month: "Apr", cost: 412 },
  { month: "May", cost: 398 },
  { month: "Jun", cost: 445 },
  { month: "Jul", cost: 421 },
  { month: "Aug", cost: 402 },
  { month: "Sep", cost: 388 },
];

const CHART_CONFIG = {
  cost: { label: "Cost", color: "var(--signal)" },
} satisfies ChartConfig;

const DUMMY_ROWS = [
  { resource: "i-0912ab3c4d5e6f701", type: "t3.medium", cpu: "3%", status: "Idle", cost: "$41.20" },
  { resource: "i-0455cd8e9f0a1b234", type: "m5.large", cpu: "88%", status: "Healthy", cost: "$96.00" },
  { resource: "vol-0a1b2c3d4e5f67890", type: "gp3 100GB", cpu: "—", status: "Unattached", cost: "$8.00" },
];

const formSchema = z.object({
  workloadName: z.string().min(2, "Too short."),
  budget: z.string().min(1, "Required."),
});

function DemoForm() {
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: { workloadName: "", budget: "" },
  });

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(() => toast.success("Form validated."))} className="flex max-w-sm flex-col gap-4">
        <FormField
          control={form.control}
          name="workloadName"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Workload name</FormLabel>
              <FormControl>
                <Input placeholder="checkout-service" {...field} />
              </FormControl>
              <FormDescription>Shown on the cost dashboard.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="budget"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Monthly budget</FormLabel>
              <FormControl>
                <Input placeholder="5000" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit">Validate</Button>
      </form>
    </Form>
  );
}

function Swatch({ name, varName }: { name: string; varName: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-8 w-8 shrink-0 rounded-md border border-border" style={{ background: `var(${varName})` }} />
      <div className="min-w-0">
        <div className="text-[12px] font-medium text-foreground">{name}</div>
        <div className="num text-[10.5px] text-ink-faint">{varName}</div>
      </div>
    </div>
  );
}

export default function StyleguidePage() {
  const [sliderVal, setSliderVal] = React.useState([40]);

  return (
    <TooltipProvider>
      <div className="min-h-screen bg-background">
        <div className="mx-auto w-full max-w-[1560px] px-4 pb-24 sm:px-6 lg:px-8">
          <header className="stage flex flex-wrap items-start justify-between gap-3 py-4 sm:py-5">
            <div className="min-w-0">
              <div className="eyebrow">CloudCare · Phase 8</div>
              <h1 className="mt-1.5 text-[clamp(1.65rem,3vw,2.35rem)] font-bold leading-[1.02] text-foreground">
                Styleguide
              </h1>
              <p className="mt-1.5 max-w-2xl text-[12.5px] leading-relaxed text-ink-faint">
                Every ported <span className="num">ui/</span> component, a <span className="num">Panel</span> and a{" "}
                <span className="num">KpiStrip</span> with dummy data — the visual regression check for this phase.
              </p>
            </div>
            <ThemeToggle />
          </header>

          {/* ================= tokens ================= */}
          <div className="mt-4">
            <Panel eyebrow="Design tokens" title="Color & type" subtitle="oklch tokens and the two custom fonts, at a glance.">
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
                <div className="space-y-3">
                  <Swatch name="Background" varName="--background" />
                  <Swatch name="Surface" varName="--surface" />
                  <Swatch name="Border" varName="--border" />
                  <Swatch name="Signal (accent)" varName="--signal" />
                </div>
                <div className="space-y-3">
                  <Swatch name="Ember (cost)" varName="--ember" />
                  <Swatch name="Mint (positive)" varName="--mint" />
                  <Swatch name="Graphite" varName="--graphite" />
                  <Swatch name="Destructive" varName="--destructive" />
                </div>
                <div className="space-y-1.5">
                  <div className="eyebrow">Display / headings</div>
                  <div className="text-2xl font-bold text-foreground">Bricolage Grotesque</div>
                  <div className="eyebrow mt-3">Sans / body</div>
                  <div className="text-base text-foreground">Inter Tight — the quick brown fox</div>
                </div>
                <div className="space-y-1.5">
                  <div className="eyebrow">Mono / numerals (tabular)</div>
                  <div className="num text-2xl text-foreground">$48,210.00</div>
                  <div className="num text-sm text-ink-faint">0123456789 · JetBrains Mono</div>
                </div>
              </div>
            </Panel>
          </div>

          {/* ================= KPI strip ================= */}
          <div className="mt-5">
            <KpiStrip kpis={DUMMY_KPIS} />
          </div>

          {/* ================= buttons / badges / toggles ================= */}
          <div className="mt-5 grid gap-5 xl:grid-cols-2">
            <Panel eyebrow="Actions" title="Buttons, badges, toggles" delay={80}>
              <div className="flex flex-wrap items-center gap-2">
                <Button>Default</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="outline">Outline</Button>
                <Button variant="ghost">Ghost</Button>
                <Button variant="destructive">Destructive</Button>
                <Button variant="link">Link</Button>
                <Button size="sm">Small</Button>
                <Button size="icon" aria-label="Settings"><Settings className="size-4" /></Button>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Badge>Default</Badge>
                <Badge variant="secondary">Secondary</Badge>
                <Badge variant="outline">Outline</Badge>
                <Badge variant="destructive">Destructive</Badge>
                <Toggle aria-label="Toggle bold">Bold</Toggle>
                <ToggleGroup type="single" defaultValue="a">
                  <ToggleGroupItem value="a">A</ToggleGroupItem>
                  <ToggleGroupItem value="b">B</ToggleGroupItem>
                  <ToggleGroupItem value="c">C</ToggleGroupItem>
                </ToggleGroup>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <Button onClick={() => toast("Toast triggered from the styleguide.")}>Fire a toast (sonner)</Button>
                <Progress value={62} className="w-40" />
              </div>
            </Panel>

            <Panel eyebrow="Overlays" title="Dialog, alert-dialog, sheet, drawer, popover, hover-card, tooltip" delay={120}>
              <div className="flex flex-wrap items-center gap-2">
                <Dialog>
                  <DialogTrigger asChild><Button variant="outline">Dialog</Button></DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Approve proposal</DialogTitle>
                      <DialogDescription>This is a dummy dialog for the styleguide.</DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                      <Button>Confirm</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>

                <AlertDialog>
                  <AlertDialogTrigger asChild><Button variant="outline">Alert dialog</Button></AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Are you sure?</AlertDialogTitle>
                      <AlertDialogDescription>This action cannot be undone.</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction>Continue</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>

                <Sheet>
                  <SheetTrigger asChild><Button variant="outline">Sheet</Button></SheetTrigger>
                  <SheetContent>
                    <SheetHeader>
                      <SheetTitle>Resource detail</SheetTitle>
                      <SheetDescription>Dummy sheet content.</SheetDescription>
                    </SheetHeader>
                    <SheetFooter>
                      <Button>Close</Button>
                    </SheetFooter>
                  </SheetContent>
                </Sheet>

                <Drawer>
                  <DrawerTrigger asChild><Button variant="outline">Drawer</Button></DrawerTrigger>
                  <DrawerContent>
                    <DrawerHeader>
                      <DrawerTitle>Quick actions</DrawerTitle>
                      <DrawerDescription>Dummy drawer content.</DrawerDescription>
                    </DrawerHeader>
                    <DrawerFooter>
                      <DrawerClose asChild><Button variant="outline">Close</Button></DrawerClose>
                    </DrawerFooter>
                  </DrawerContent>
                </Drawer>

                <Popover>
                  <PopoverTrigger asChild><Button variant="outline">Popover</Button></PopoverTrigger>
                  <PopoverContent>Dummy popover content.</PopoverContent>
                </Popover>

                <HoverCard>
                  <HoverCardTrigger asChild><Button variant="outline">Hover card</Button></HoverCardTrigger>
                  <HoverCardContent>Dummy hover card content.</HoverCardContent>
                </HoverCard>

                <Tooltip>
                  <TooltipTrigger asChild><Button variant="outline">Tooltip</Button></TooltipTrigger>
                  <TooltipContent>Dummy tooltip</TooltipContent>
                </Tooltip>
              </div>
            </Panel>
          </div>

          {/* ================= menus ================= */}
          <div className="mt-5 grid gap-5 xl:grid-cols-2">
            <Panel eyebrow="Menus" title="Dropdown, context, menubar, navigation" delay={140}>
              <div className="flex flex-wrap items-center gap-3">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild><Button variant="outline">Dropdown</Button></DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuLabel>Actions</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem>Approve</DropdownMenuItem>
                    <DropdownMenuItem>Reject</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>

                <ContextMenu>
                  <ContextMenuTrigger asChild>
                    <div className="flex h-9 items-center rounded-md border border-dashed border-border px-3 text-[12.5px] text-ink-faint">
                      Right-click me
                    </div>
                  </ContextMenuTrigger>
                  <ContextMenuContent>
                    <ContextMenuItem>Copy resource id</ContextMenuItem>
                    <ContextMenuItem>Open in AWS console</ContextMenuItem>
                  </ContextMenuContent>
                </ContextMenu>

                <Menubar>
                  <MenubarMenu>
                    <MenubarTrigger>File</MenubarTrigger>
                    <MenubarContent>
                      <MenubarItem>Export CSV</MenubarItem>
                      <MenubarItem>Print</MenubarItem>
                    </MenubarContent>
                  </MenubarMenu>
                </Menubar>
              </div>

              <NavigationMenu className="mt-4">
                <NavigationMenuList>
                  <NavigationMenuItem>
                    <NavigationMenuTrigger>Resources</NavigationMenuTrigger>
                    <NavigationMenuContent>
                      <div className="w-48 p-2">
                        <NavigationMenuLink className="block rounded px-2 py-1.5 text-[12.5px] hover:bg-accent">
                          Compute
                        </NavigationMenuLink>
                        <NavigationMenuLink className="block rounded px-2 py-1.5 text-[12.5px] hover:bg-accent">
                          Storage
                        </NavigationMenuLink>
                      </div>
                    </NavigationMenuContent>
                  </NavigationMenuItem>
                </NavigationMenuList>
              </NavigationMenu>
            </Panel>

            <Panel eyebrow="Disclosure" title="Tabs, accordion, collapsible" delay={160}>
              <Tabs defaultValue="overview">
                <TabsList>
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="details">Details</TabsTrigger>
                </TabsList>
                <TabsContent value="overview" className="text-[12.5px] text-ink-dim">Overview panel content.</TabsContent>
                <TabsContent value="details" className="text-[12.5px] text-ink-dim">Details panel content.</TabsContent>
              </Tabs>

              <Accordion type="single" collapsible className="mt-4">
                <AccordionItem value="a">
                  <AccordionTrigger>What is a proposal?</AccordionTrigger>
                  <AccordionContent>A deterministic, scored recommendation awaiting approval.</AccordionContent>
                </AccordionItem>
                <AccordionItem value="b">
                  <AccordionTrigger>What is the allowlist tag?</AccordionTrigger>
                  <AccordionContent>A hard gate — no resource without it may ever be mutated.</AccordionContent>
                </AccordionItem>
              </Accordion>

              <Collapsible className="mt-4">
                <CollapsibleTrigger asChild><Button variant="ghost" size="sm">Toggle raw evidence</Button></CollapsibleTrigger>
                <CollapsibleContent className="mt-2 text-[12px] text-ink-faint">cpu_p95: 2.1%, window_days: 14</CollapsibleContent>
              </Collapsible>
            </Panel>
          </div>

          {/* ================= form controls ================= */}
          <div className="mt-5 grid gap-5 xl:grid-cols-2">
            <Panel eyebrow="Inputs" title="Text, select, checkbox, radio, switch, slider" delay={180}>
              <div className="grid max-w-sm gap-4">
                <div className="grid gap-1.5">
                  <Label htmlFor="sg-input">Resource name</Label>
                  <Input id="sg-input" placeholder="i-0912ab3c4d5e6f701" />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="sg-textarea">Rejection reason</Label>
                  <Textarea id="sg-textarea" placeholder="Not this month…" />
                </div>
                <div className="grid gap-1.5">
                  <Label>Provider</Label>
                  <Select defaultValue="aws">
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="aws">AWS</SelectItem>
                      <SelectItem value="azure">Azure</SelectItem>
                      <SelectItem value="vps">VPS</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox id="sg-checkbox" defaultChecked />
                  <Label htmlFor="sg-checkbox">Require human approval</Label>
                </div>
                <RadioGroup defaultValue="low">
                  <div className="flex items-center gap-2"><RadioGroupItem value="low" id="sg-r1" /><Label htmlFor="sg-r1">Low risk</Label></div>
                  <div className="flex items-center gap-2"><RadioGroupItem value="high" id="sg-r2" /><Label htmlFor="sg-r2">High risk</Label></div>
                </RadioGroup>
                <div className="flex items-center gap-2">
                  <Switch id="sg-switch" defaultChecked />
                  <Label htmlFor="sg-switch">Auto-execute</Label>
                </div>
                <div className="grid gap-1.5">
                  <Label>Confidence threshold ({sliderVal[0]}%)</Label>
                  <Slider value={sliderVal} onValueChange={setSliderVal} max={100} step={1} />
                </div>
                <InputOTP maxLength={4}>
                  <InputOTPGroup>
                    <InputOTPSlot index={0} />
                    <InputOTPSlot index={1} />
                    <InputOTPSlot index={2} />
                    <InputOTPSlot index={3} />
                  </InputOTPGroup>
                </InputOTP>
              </div>
            </Panel>

            <Panel eyebrow="Forms" title="react-hook-form + zod" subtitle="FormField wired through Form's context." delay={200}>
              <DemoForm />
            </Panel>
          </div>

          {/* ================= data display ================= */}
          <div className="mt-5 grid gap-5 xl:grid-cols-3">
            <Panel eyebrow="Layout" title="Card, avatar, alert, skeleton" className="xl:col-span-1" delay={220}>
              <Card>
                <CardHeader>
                  <CardTitle>i-0912ab3c4d5e6f701</CardTitle>
                  <CardDescription>t3.medium · ap-south-1</CardDescription>
                </CardHeader>
                <CardContent className="flex items-center gap-3">
                  <Avatar>
                    <AvatarImage src="" alt="" />
                    <AvatarFallback>CC</AvatarFallback>
                  </Avatar>
                  <div className="num text-sm text-foreground">$41.20/mo</div>
                </CardContent>
                <CardFooter><Button size="sm" variant="outline">View</Button></CardFooter>
              </Card>
              <Alert className="mt-4">
                <AlertTitle>Idle resource detected</AlertTitle>
                <AlertDescription>CPU p95 below 5% for 14 days.</AlertDescription>
              </Alert>
              <div className="mt-4 space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            </Panel>

            <Panel eyebrow="Data" title="Table" className="xl:col-span-2" delay={240}>
              <Table>
                <TableCaption>Sample resources — dummy data.</TableCaption>
                <TableHeader>
                  <TableRow>
                    <TableHead>Resource</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>CPU p95</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Monthly cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {DUMMY_ROWS.map((r) => (
                    <TableRow key={r.resource}>
                      <TableCell className="num">{r.resource}</TableCell>
                      <TableCell>{r.type}</TableCell>
                      <TableCell className="num">{r.cpu}</TableCell>
                      <TableCell>{r.status}</TableCell>
                      <TableCell className="num text-right">{r.cost}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              <Breadcrumb className="mt-4">
                <BreadcrumbList>
                  <BreadcrumbItem><BreadcrumbLink href="#">Resources</BreadcrumbLink></BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem><BreadcrumbPage>i-0912ab3c4d5e6f701</BreadcrumbPage></BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>

              <Pagination className="mt-4">
                <PaginationContent>
                  <PaginationItem><PaginationPrevious href="#" /></PaginationItem>
                  <PaginationItem><PaginationLink href="#" isActive>1</PaginationLink></PaginationItem>
                  <PaginationItem><PaginationLink href="#">2</PaginationLink></PaginationItem>
                  <PaginationItem><PaginationEllipsis /></PaginationItem>
                  <PaginationItem><PaginationNext href="#" /></PaginationItem>
                </PaginationContent>
              </Pagination>
            </Panel>
          </div>

          {/* ================= chart / calendar / command / carousel ================= */}
          <div className="mt-5 grid gap-5 xl:grid-cols-2">
            <Panel eyebrow="Charts" title="recharts via chart.tsx" delay={260}>
              <ChartContainer config={CHART_CONFIG} className="h-[220px] w-full">
                <BarChart data={DUMMY_CHART_DATA}>
                  <CartesianGrid vertical={false} stroke="var(--grid-line)" />
                  <XAxis dataKey="month" tickLine={false} axisLine={false} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="cost" fill="var(--color-cost)" radius={4} />
                </BarChart>
              </ChartContainer>
            </Panel>

            <Panel eyebrow="Pickers" title="Calendar, command palette" delay={280}>
              <div className="flex flex-wrap gap-6">
                <Calendar mode="single" className="rounded-md border border-border p-2" />
                <Command className="w-64 rounded-md border border-border">
                  <CommandInput placeholder="Search resources…" />
                  <CommandList>
                    <CommandEmpty>No results.</CommandEmpty>
                    <CommandGroup heading="Resources">
                      <CommandItem>i-0912ab3c4d5e6f701</CommandItem>
                      <CommandItem>i-0455cd8e9f0a1b234</CommandItem>
                    </CommandGroup>
                  </CommandList>
                </Command>
              </div>
            </Panel>
          </div>

          <div className="mt-5 grid gap-5 xl:grid-cols-2">
            <Panel eyebrow="Motion" title="Carousel" delay={300}>
              <Carousel className="w-full max-w-sm">
                <CarouselContent>
                  {["AWS", "Azure", "VPS"].map((p) => (
                    <CarouselItem key={p}>
                      <div className="flex h-32 items-center justify-center rounded-md border border-border text-foreground">{p}</div>
                    </CarouselItem>
                  ))}
                </CarouselContent>
                <CarouselPrevious />
                <CarouselNext />
              </Carousel>
            </Panel>

            <Panel eyebrow="Layout" title="Resizable panels, scroll area, aspect ratio, separator" delay={320}>
              <ResizablePanelGroup orientation="horizontal" className="h-32 rounded-md border border-border">
                <ResizablePanel defaultSize={50} className="flex items-center justify-center text-[12.5px] text-ink-faint">Left</ResizablePanel>
                <ResizableHandle withHandle />
                <ResizablePanel defaultSize={50} className="flex items-center justify-center text-[12.5px] text-ink-faint">Right</ResizablePanel>
              </ResizablePanelGroup>

              <ScrollArea className="mt-4 h-24 w-full rounded-md border border-border p-3">
                <p className="text-[12.5px] leading-relaxed text-ink-dim">
                  A long scrollable block of text to demonstrate the scroll area component and its
                  themed scrollbar thumb, which should pick up the --color-hairline token in both
                  light and dark mode.
                </p>
              </ScrollArea>

              <Separator className="my-4" />

              <div className="w-40">
                <AspectRatio ratio={16 / 9} className="rounded-md bg-muted" />
              </div>
            </Panel>
          </div>

          {/* ================= sidebar ================= */}
          <div className="mt-5">
            <Panel eyebrow="Navigation" title="Sidebar" delay={340} bodyClassName="p-0">
              <SidebarProvider className="min-h-[280px]">
                <Sidebar collapsible="none" className="border-r border-border">
                  <SidebarHeader className="p-3 text-[12.5px] font-semibold">CloudCare</SidebarHeader>
                  <SidebarContent>
                    <SidebarGroup>
                      <SidebarGroupLabel>Overview</SidebarGroupLabel>
                      <SidebarGroupContent>
                        <SidebarMenu>
                          <SidebarMenuItem>
                            <SidebarMenuButton>
                              <Home /> <span>Dashboard</span>
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                          <SidebarMenuItem>
                            <SidebarMenuButton>
                              <Inbox /> <span>Proposals</span>
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                          <SidebarMenuItem>
                            <SidebarMenuButton>
                              <CalIcon /> <span>Reports</span>
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                        </SidebarMenu>
                      </SidebarGroupContent>
                    </SidebarGroup>
                  </SidebarContent>
                </Sidebar>
                <div className="flex flex-1 items-center gap-2 p-4">
                  <SidebarTrigger />
                  <span className="text-[12.5px] text-ink-faint">Sidebar content area.</span>
                </div>
              </SidebarProvider>
            </Panel>
          </div>

          <footer className="stage mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-5">
            <p className="num text-[10.5px] tracking-[0.04em] text-ink-faint">CloudCare · Phase 8 styleguide</p>
            <p className="num text-[10.5px] tracking-[0.04em] text-ink-faint">46 ui/ components · dummy data only</p>
          </footer>
        </div>
      </div>
    </TooltipProvider>
  );
}
