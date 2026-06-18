from __future__ import annotations

import queue
import tkinter as tk
from typing import Any

import customtkinter as ctk

from protocol import (
    FLAG_CARRY,
    FLAG_DIV_ZERO,
    FLAG_NEGATIVE,
    FLAG_OVERFLOW,
    FLAG_ZERO,
    HelloFrame,
    MemoryFrame,
    SnapshotFrame,
    decode_eeprom_history,
    sram_meaning,
)
from serial_worker import SerialWorker, SourceEvent, list_serial_ports
from simulator import SimulatorWorker
from widgets import ByteRegisterWidget, MemoryHeatmap, MetricWidget


BG = "#071013"
SURFACE = "#0E1A1E"
SURFACE_ALT = "#14272D"
BORDER = "#21434B"
TEXT = "#EAF2F5"
MUTED = "#83A0A8"
CYAN = "#00D9FF"
GREEN = "#3BEE7A"
AMBER = "#FFB84D"
RED = "#FF4F70"
BLUE = "#4C7DFF"
OFF = "#22333A"


class AvrXrayApp(ctk.CTk):
    def __init__(
        self,
        initial_port: str | None = None,
        baud: int = 115200,
        simulate: bool = False,
    ):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.initial_port = initial_port
        self.default_baud = baud
        self.events: queue.Queue[SourceEvent] = queue.Queue()
        self.source: SerialWorker | SimulatorWorker | None = None
        self.connection_state = "disconnected"
        self.latest_snapshot: SnapshotFrame | None = None
        self.latest_memory: MemoryFrame | None = None

        self.port_var = tk.StringVar(value=initial_port or "Auto")
        self.baud_var = tk.StringVar(value=str(baud))
        self.simulate_var = tk.BooleanVar(value=simulate)
        self.status_var = tk.StringVar(value="Desconectado")
        self.device_var = tk.StringVar(value="Aguardando dispositivo")
        self.sequence_var = tk.StringVar(value="seq --")
        self.uptime_var = tk.StringVar(value="uptime --")
        self.inspector_var = tk.StringVar(
            value="SRAM[0]\nDec: 0  Hex: 0x00  Bin: 00000000\nULA operand A"
        )

        self.title("AVR X-Ray - ATmega328P Internal Monitor")
        self.geometry("1280x820")
        self.minsize(1080, 700)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.ula_metrics: dict[str, MetricWidget] = {}
        self.ula_flags: dict[str, ctk.CTkLabel] = {}
        self.sreg_flags: dict[str, ctk.CTkLabel] = {}
        self.port_widgets: dict[str, dict[str, ByteRegisterWidget]] = {}
        self.timer_metrics: dict[str, MetricWidget] = {}

        self._build_layout()
        self._refresh_ports()
        self.after(50, self._poll_events)

        if simulate or initial_port:
            self.after(180, self._connect)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        self.tabview = ctk.CTkTabview(
            self,
            fg_color=BG,
            border_color=BORDER,
            border_width=1,
            segmented_button_fg_color=SURFACE,
            segmented_button_selected_color=CYAN,
            segmented_button_selected_hover_color="#00B8D9",
            segmented_button_unselected_color=OFF,
            segmented_button_unselected_hover_color="#314A54",
            text_color=TEXT,
        )
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 10))

        self.overview_tab = self.tabview.add("Visao Geral")
        self.ports_tab = self.tabview.add("Portas")
        self.timers_tab = self.tabview.add("Timers")
        self.memory_tab = self.tabview.add("Memoria")

        for tab in (
            self.overview_tab,
            self.ports_tab,
            self.timers_tab,
            self.memory_tab,
        ):
            tab.configure(fg_color=BG)

        self._build_overview_tab()
        self._build_ports_tab()
        self._build_timers_tab()
        self._build_memory_tab()

        footer = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 12))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            footer,
            textvariable=self.status_var,
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            footer,
            textvariable=self.sequence_var,
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=12),
        ).grid(row=0, column=1, padx=14)
        ctk.CTkLabel(
            footer,
            textvariable=self.uptime_var,
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=12),
        ).grid(row=0, column=2)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="AVR X-Ray",
            text_color=TEXT,
            font=ctk.CTkFont(size=29, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            textvariable=self.device_var,
            text_color=MUTED,
            font=ctk.CTkFont(size=13),
        ).grid(row=1, column=0, sticky="w", pady=(1, 0))

        controls = ctk.CTkFrame(header, fg_color=BG, corner_radius=0)
        controls.grid(row=0, column=1, rowspan=2, sticky="e")

        self.port_combo = ctk.CTkComboBox(
            controls,
            variable=self.port_var,
            values=["Auto"],
            width=150,
            height=36,
            fg_color=SURFACE,
            border_color=BORDER,
            button_color=OFF,
            button_hover_color="#314A54",
            dropdown_fg_color=SURFACE,
        )
        self.port_combo.grid(row=0, column=0, padx=4)

        ctk.CTkButton(
            controls,
            text="Atualizar",
            command=self._refresh_ports,
            width=84,
            height=36,
            fg_color=OFF,
            hover_color="#314A54",
        ).grid(row=0, column=1, padx=4)

        self.baud_entry = ctk.CTkEntry(
            controls,
            textvariable=self.baud_var,
            width=90,
            height=36,
            fg_color=SURFACE,
            border_color=BORDER,
            justify="center",
        )
        self.baud_entry.grid(row=0, column=2, padx=4)

        self.simulate_switch = ctk.CTkSwitch(
            controls,
            text="Simular",
            variable=self.simulate_var,
            onvalue=True,
            offvalue=False,
            progress_color=BLUE,
            button_color=TEXT,
        )
        self.simulate_switch.grid(row=0, column=3, padx=(8, 6))

        self.connect_button = ctk.CTkButton(
            controls,
            text="Conectar",
            command=self._toggle_connection,
            width=112,
            height=36,
            fg_color=GREEN,
            hover_color="#2FC765",
            text_color="#04120A",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.connect_button.grid(row=0, column=4, padx=4)

        self.status_badge = ctk.CTkLabel(
            controls,
            text="OFFLINE",
            width=92,
            height=32,
            corner_radius=7,
            fg_color=OFF,
            text_color=MUTED,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.status_badge.grid(row=0, column=5, padx=(8, 0))

    def _build_overview_tab(self) -> None:
        tab = self.overview_tab
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=2)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, fg_color=SURFACE, border_color=BORDER, border_width=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        left.grid_columnconfigure((0, 1, 2), weight=1, uniform="ula")

        ctk.CTkLabel(
            left,
            text="ULA 4 bits",
            text_color=TEXT,
            font=ctk.CTkFont(size=19, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 9))

        metric_specs = (
            ("a", "A"),
            ("b", "B"),
            ("operation", "Operacao"),
            ("result", "Resultado"),
            ("input", "Entrada atual"),
            ("stage", "Etapa"),
        )
        for index, (key, title) in enumerate(metric_specs):
            widget = MetricWidget(left, title)
            widget.grid(
                row=1 + index // 3,
                column=index % 3,
                sticky="ew",
                padx=7,
                pady=7,
            )
            self.ula_metrics[key] = widget

        flag_frame = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0)
        flag_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=9, pady=(12, 14))
        flag_frame.grid_columnconfigure(tuple(range(5)), weight=1, uniform="flags")
        for column, name in enumerate(("Z", "C", "N", "V", "D")):
            label = ctk.CTkLabel(
                flag_frame,
                text=f"{name}\n0",
                height=58,
                corner_radius=6,
                fg_color=OFF,
                text_color=MUTED,
                font=ctk.CTkFont(size=16, weight="bold"),
            )
            label.grid(row=0, column=column, sticky="ew", padx=4)
            self.ula_flags[name] = label

        right = ctk.CTkFrame(tab, fg_color=SURFACE, border_color=BORDER, border_width=1)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text="CPU Status Register",
            text_color=TEXT,
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        self.sreg_register = ByteRegisterWidget(right, "SREG")
        self.sreg_register.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        sreg_frame = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        sreg_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        sreg_frame.grid_columnconfigure(tuple(range(8)), weight=1, uniform="sreg")
        for column, name in enumerate(("I", "T", "H", "S", "V", "N", "Z", "C")):
            label = ctk.CTkLabel(
                sreg_frame,
                text=f"{name}\n0",
                height=43,
                corner_radius=5,
                fg_color=OFF,
                text_color=MUTED,
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            label.grid(row=0, column=column, sticky="ew", padx=2)
            self.sreg_flags[name] = label

        ctk.CTkLabel(
            right,
            text="ADC A0",
            text_color=TEXT,
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=3, column=0, sticky="w", padx=16, pady=(12, 8))

        adc_metrics = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        adc_metrics.grid(row=4, column=0, sticky="ew", padx=12)
        adc_metrics.grid_columnconfigure((0, 1), weight=1, uniform="adc")
        self.adc_raw = MetricWidget(adc_metrics, "Leitura", "0 / 1023")
        self.adc_raw.grid(row=0, column=0, sticky="ew", padx=4)
        self.adc_voltage = MetricWidget(adc_metrics, "Tensao", "0.000 V", GREEN)
        self.adc_voltage.grid(row=0, column=1, sticky="ew", padx=4)

        self.adc_bar = ctk.CTkProgressBar(
            right,
            height=18,
            fg_color=OFF,
            progress_color=GREEN,
            border_color=BORDER,
            border_width=1,
        )
        self.adc_bar.grid(row=5, column=0, sticky="ew", padx=16, pady=(12, 16))
        self.adc_bar.set(0)

    def _build_ports_tab(self) -> None:
        tab = self.ports_tab
        tab.grid_columnconfigure((0, 1, 2), weight=1, uniform="ports")
        tab.grid_rowconfigure(0, weight=1)

        for column, port_name in enumerate(("B", "C", "D")):
            section = ctk.CTkFrame(
                tab,
                fg_color=SURFACE,
                border_color=BORDER,
                border_width=1,
            )
            section.grid(row=0, column=column, sticky="nsew", padx=7, pady=12)
            section.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                section,
                text=f"PORT {port_name}",
                text_color=TEXT,
                font=ctk.CTkFont(size=18, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 9))

            widgets: dict[str, ByteRegisterWidget] = {}
            for row, register in enumerate(("DDR", "PORT", "PIN"), start=1):
                widget = ByteRegisterWidget(section, f"{register}{port_name}")
                widget.grid(row=row, column=0, sticky="ew", padx=12, pady=7)
                widgets[register.lower()] = widget
            self.port_widgets[port_name] = widgets

    def _build_timers_tab(self) -> None:
        tab = self.timers_tab
        tab.grid_columnconfigure((0, 1, 2), weight=1, uniform="timers")
        tab.grid_rowconfigure(0, weight=1)

        timer_specs = {
            "Timer 0": ("tcnt0", "tccr0a", "tccr0b"),
            "Timer 1": ("tcnt1", "tccr1a", "tccr1b"),
            "Timer 2": ("tcnt2", "tccr2a", "tccr2b"),
        }
        for column, (title, keys) in enumerate(timer_specs.items()):
            section = ctk.CTkFrame(
                tab,
                fg_color=SURFACE,
                border_color=BORDER,
                border_width=1,
            )
            section.grid(row=0, column=column, sticky="nsew", padx=7, pady=12)
            section.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                section,
                text=title,
                text_color=TEXT,
                font=ctk.CTkFont(size=18, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 10))

            for row, key in enumerate(keys, start=1):
                metric = MetricWidget(section, key.upper())
                metric.grid(row=row, column=0, sticky="ew", padx=12, pady=7)
                self.timer_metrics[key] = metric

        ctk.CTkLabel(
            tab,
            text="Os registradores sao apenas observados; o dashboard nao altera a configuracao dos timers.",
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, columnspan=3, pady=(0, 10))

    def _build_memory_tab(self) -> None:
        tab = self.memory_tab
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=2)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, fg_color=SURFACE, border_color=BORDER, border_width=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left,
            text="SRAM ula_probe[128]",
            text_color=TEXT,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))

        self.heatmap = MemoryHeatmap(left, on_select=self._inspect_sram)
        self.heatmap.grid(row=1, column=0, padx=12, pady=(0, 8))

        self.inspector_label = ctk.CTkLabel(
            left,
            textvariable=self.inspector_var,
            height=62,
            corner_radius=7,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            justify="left",
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.inspector_label.grid(row=2, column=0, sticky="ew", padx=14, pady=(4, 14))

        right = ctk.CTkFrame(tab, fg_color=SURFACE, border_color=BORDER, border_width=1)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        toolbar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        toolbar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            toolbar,
            text="Memorias estaticas",
            text_color=TEXT,
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            toolbar,
            text="GET_STATIC",
            command=self._request_static,
            width=112,
            height=32,
            fg_color=BLUE,
            hover_color="#3D66CE",
        ).grid(row=0, column=1, sticky="e")

        static_tabs = ctk.CTkTabview(
            right,
            fg_color=SURFACE,
            segmented_button_fg_color=OFF,
            segmented_button_selected_color=CYAN,
            segmented_button_selected_hover_color="#00B8D9",
            segmented_button_unselected_color=SURFACE_ALT,
            segmented_button_unselected_hover_color="#314A54",
            text_color=TEXT,
        )
        static_tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        eeprom_tab = static_tabs.add("EEPROM")
        history_tab = static_tabs.add("Historico")
        flash_tab = static_tabs.add("FLASH")

        for memory_tab in (eeprom_tab, history_tab, flash_tab):
            memory_tab.configure(fg_color=SURFACE)
            memory_tab.grid_columnconfigure(0, weight=1)
            memory_tab.grid_rowconfigure(0, weight=1)

        self.eeprom_text = self._memory_textbox(eeprom_tab)
        self.history_text = self._memory_textbox(history_tab)
        self.flash_text = self._memory_textbox(flash_tab)
        self._set_text(self.eeprom_text, "Aguardando GET_STATIC...")
        self._set_text(self.history_text, "Historico EEPROM indisponivel.")
        self._set_text(
            self.flash_text,
            "FLASH e somente leitura e normalmente nao muda durante a execucao.",
        )

    def _memory_textbox(self, parent: ctk.CTkFrame) -> ctk.CTkTextbox:
        textbox = ctk.CTkTextbox(
            parent,
            fg_color="#09171B",
            border_color=BORDER,
            border_width=1,
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none",
        )
        textbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        return textbox

    def _toggle_connection(self) -> None:
        if self.connection_state in {"connecting", "connected"}:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        self._disconnect_source()
        try:
            baud = int(self.baud_var.get().strip())
            if baud <= 0:
                raise ValueError
        except ValueError:
            self._set_status("Baud rate invalido.", "error")
            return

        if self.simulate_var.get():
            self.source = SimulatorWorker(self.events)
        else:
            selected_port = self.port_var.get().strip()
            port = None if selected_port in {"", "Auto"} else selected_port
            self.source = SerialWorker(self.events, port=port, baud=baud)

        self.connection_state = "connecting"
        self._refresh_connection_controls()
        self.source.start()

    def _disconnect(self) -> None:
        self._disconnect_source()
        self.connection_state = "disconnected"
        self._set_status("Desconectado.", "offline")
        self.device_var.set("Aguardando dispositivo")
        self._refresh_connection_controls()

    def _disconnect_source(self) -> None:
        if self.source is not None:
            self.source.stop()
        self.source = None

    def _request_static(self) -> None:
        if self.source is None:
            self._set_status("Conecte antes de pedir EEPROM/FLASH.", "error")
            return
        self.source.request_static()
        self._set_status("GET_STATIC enviado.", "connected")

    def _refresh_ports(self) -> None:
        available = list_serial_ports()
        values = ["Auto", *(device for device, _ in available)]
        current = self.port_var.get()
        if self.initial_port and self.initial_port not in values:
            values.append(self.initial_port)
        self.port_combo.configure(values=values)
        if current not in values:
            self.port_var.set("Auto")

    def _poll_events(self) -> None:
        for _ in range(200):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        self.after(50, self._poll_events)

    def _handle_event(self, event: SourceEvent) -> None:
        if event.kind == "status":
            self.connection_state = str(event.data)
            if event.data == "connected":
                self._set_status(event.message, "connected")
            elif event.data == "connecting":
                self._set_status(event.message, "connecting")
            elif self.source is None or not self.source.running:
                self._set_status(event.message, "offline")
            self._refresh_connection_controls()
            return

        if event.kind in {"error", "protocol_error"}:
            self._set_status(event.message, "error")
            if event.kind == "error":
                self.connection_state = "disconnected"
                self._refresh_connection_controls()
            return

        if event.kind == "frame":
            frame = event.data
            if isinstance(frame, HelloFrame):
                self.device_var.set(
                    f"{frame.device} | firmware {frame.firmware} | {frame.sample_hz} Hz"
                )
            elif isinstance(frame, SnapshotFrame):
                self.latest_snapshot = frame
                self._render_snapshot(frame)
            elif isinstance(frame, MemoryFrame):
                self.latest_memory = frame
                self._render_memory(frame)

    def _render_snapshot(self, frame: SnapshotFrame) -> None:
        ula = frame.ula
        self.sequence_var.set(f"seq {frame.sequence}")
        self.uptime_var.set(f"uptime {frame.millis / 1000:,.1f}s")

        self.ula_metrics["a"].set(f"{ula.a:02d} / {ula.a:04b}")
        self.ula_metrics["b"].set(f"{ula.b:02d} / {ula.b:04b}")
        self.ula_metrics["operation"].set(
            f"{ula.operation} {ula.operation_name}"
        )
        self.ula_metrics["result"].set(f"{ula.result:02d} / {ula.result:04b}")
        self.ula_metrics["input"].set(
            f"{ula.input_value:02d} / {ula.input_value:04b}"
        )
        self.ula_metrics["stage"].set(ula.stage_name)

        flag_map = {
            "Z": bool(ula.flags & FLAG_ZERO),
            "C": bool(ula.flags & FLAG_CARRY),
            "N": bool(ula.flags & FLAG_NEGATIVE),
            "V": bool(ula.flags & FLAG_OVERFLOW),
            "D": bool(ula.flags & FLAG_DIV_ZERO),
        }
        for name, active in flag_map.items():
            warning = name in {"V", "D"} and active
            self.ula_flags[name].configure(
                text=f"{name}\n{int(active)}",
                fg_color=RED if warning else CYAN if active else OFF,
                text_color="#031014" if active else MUTED,
            )

        self.sreg_register.set_value(frame.sreg)
        for name, bit in zip(
            ("I", "T", "H", "S", "V", "N", "Z", "C"),
            range(7, -1, -1),
        ):
            active = bool(frame.sreg & (1 << bit))
            self.sreg_flags[name].configure(
                text=f"{name}\n{int(active)}",
                fg_color=CYAN if active else OFF,
                text_color="#031014" if active else MUTED,
            )

        for port_name, state in frame.ports.items():
            widgets = self.port_widgets[port_name]
            widgets["ddr"].set_value(state.ddr)
            widgets["port"].set_value(state.port)
            widgets["pin"].set_value(state.pin)

        for key, metric in self.timer_metrics.items():
            value = getattr(frame.timers, key)
            width = 4 if key == "tcnt1" else 2
            metric.set(f"{value} / 0x{value:0{width}X}")

        self.adc_raw.set(f"{frame.adc.a0} / 1023")
        self.adc_voltage.set(f"{frame.adc.volts:.3f} V")
        self.adc_bar.set(frame.adc.a0 / 1023)
        self.heatmap.update_bytes(frame.sram)
        self._inspect_sram(self.heatmap.selected_index, frame.sram[self.heatmap.selected_index])

    def _render_memory(self, frame: MemoryFrame) -> None:
        self._set_text(self.eeprom_text, self._hex_dump(frame.eeprom))
        self._set_text(
            self.flash_text,
            "FLASH program memory - read only during runtime\n\n"
            + self._hex_dump(frame.flash),
        )

        records = decode_eeprom_history(frame.eeprom)
        if not records:
            history = "Nenhum historico valido encontrado na EEPROM."
        else:
            lines = ["#  A  B  OP       R  FLAGS", "-- -- -- -------- -- -----"]
            for number, record in enumerate(records):
                lines.append(
                    f"{number:02d} {record['a']:02d} {record['b']:02d} "
                    f"{record['operation_name']:<8} {record['result']:02d} "
                    f"0x{record['flags']:02X}"
                )
            history = "\n".join(lines)
        self._set_text(self.history_text, history)
        self._set_status("EEPROM e FLASH atualizadas.", "connected")

    def _inspect_sram(self, index: int, value: int) -> None:
        self.inspector_var.set(
            f"SRAM[{index}]  address offset 0x{index:02X}\n"
            f"Dec: {value:3d}  Hex: 0x{value:02X}  Bin: {value:08b}\n"
            f"{sram_meaning(index)}"
        )

    def _refresh_connection_controls(self) -> None:
        connected = self.connection_state in {"connecting", "connected"}
        self.connect_button.configure(
            text="Desconectar" if connected else "Conectar",
            fg_color=RED if connected else GREEN,
            hover_color="#D33D59" if connected else "#2FC765",
            text_color=TEXT if connected else "#04120A",
        )

    def _set_status(self, message: str, state: str) -> None:
        self.status_var.set(message)
        styles = {
            "connected": (GREEN, "#04120A", "ONLINE"),
            "connecting": (AMBER, "#1A1200", "CONNECT"),
            "error": (RED, TEXT, "ERRO"),
            "offline": (OFF, MUTED, "OFFLINE"),
        }
        background, foreground, text = styles.get(state, styles["offline"])
        self.status_badge.configure(
            text=text,
            fg_color=background,
            text_color=foreground,
        )

    @staticmethod
    def _hex_dump(data: bytes, width: int = 16) -> str:
        lines = []
        for offset in range(0, len(data), width):
            chunk = data[offset : offset + width]
            hex_part = " ".join(f"{value:02X}" for value in chunk)
            binary = " ".join(f"{value:08b}" for value in chunk[:4])
            lines.append(f"{offset:04X}: {hex_part:<47}  {binary}")
        return "\n".join(lines)

    @staticmethod
    def _set_text(textbox: ctk.CTkTextbox, text: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")

    def _on_close(self) -> None:
        self._disconnect_source()
        self.destroy()


def run_gui(
    initial_port: str | None = None,
    baud: int = 115200,
    simulate: bool = False,
) -> None:
    app = AvrXrayApp(
        initial_port=initial_port,
        baud=baud,
        simulate=simulate,
    )
    app.mainloop()
