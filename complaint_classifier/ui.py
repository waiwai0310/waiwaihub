"""
UI 界面模块
负责用户交互和弹窗显示
"""

import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Optional, Tuple
import os
import sys


class UIManager:
    """UI 管理器"""

    @staticmethod
    def _use_gui_popup() -> bool:
        """
        是否启用 GUI 弹窗。
        环境变量 COMPLAINT_UI_POPUP:
          - 1/true/yes/on  强制启用
          - 0/false/no/off 强制禁用
          - 未设置         仅在交互终端启用
        """
        v = str(os.environ.get("COMPLAINT_UI_POPUP", "")).strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
        # 默认：非交互环境禁用，避免自动化任务阻塞在弹窗
        return bool(getattr(sys.stdout, "isatty", lambda: False)())

    @staticmethod
    def _print_fallback(level: str, title: str, message: str) -> None:
        print(f"[{level}] {title}: {message}", flush=True)
    
    @staticmethod
    def show_info(title: str, message: str) -> None:
        """
        显示信息弹窗
        
        Args:
            title: 弹窗标题
            message: 弹窗内容
        """
        if not UIManager._use_gui_popup():
            UIManager._print_fallback("INFO", title, message)
            return
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(title, message)
            root.destroy()
        except Exception:
            UIManager._print_fallback("INFO", title, message)
    
    @staticmethod
    def show_error(title: str, message: str) -> None:
        """
        显示错误弹窗
        
        Args:
            title: 弹窗标题
            message: 弹窗内容
        """
        if not UIManager._use_gui_popup():
            UIManager._print_fallback("ERROR", title, message)
            return
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(title, message)
            root.destroy()
        except Exception:
            UIManager._print_fallback("ERROR", title, message)
    
    @staticmethod
    def show_warning(title: str, message: str) -> None:
        """
        显示警告弹窗
        
        Args:
            title: 弹窗标题
            message: 弹窗内容
        """
        if not UIManager._use_gui_popup():
            UIManager._print_fallback("WARN", title, message)
            return
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning(title, message)
            root.destroy()
        except Exception:
            UIManager._print_fallback("WARN", title, message)
    
    @staticmethod
    def ask_yes_no(title: str, message: str) -> bool:
        """
        显示是/否问询弹窗
        
        Args:
            title: 弹窗标题
            message: 弹窗内容
        
        Returns:
            用户选择（True = 是，False = 否）
        """
        root = tk.Tk()
        root.withdraw()
        result = messagebox.askyesno(title, message)
        root.destroy()
        return result
    
    @staticmethod
    def ask_ok_cancel(title: str, message: str) -> bool:
        """
        显示确定/取消问询弹窗
        
        Args:
            title: 弹窗标题
            message: 弹窗内容
        
        Returns:
            用户选择（True = 确定，False = 取消）
        """
        root = tk.Tk()
        root.withdraw()
        result = messagebox.askokcancel(title, message)
        root.destroy()
        return result
    
    @staticmethod
    def select_file(
        title: str = "选择文件",
        filetypes: list = None,
        initialdir: str = None
    ) -> Optional[str]:
        """
        选择文件
        
        Args:
            title: 对话框标题
            filetypes: 文件类型列表，如 [("Excel", "*.xlsx"), ("All Files", "*.*")]
            initialdir: 初始目录
        
        Returns:
            选中的文件路径，如果取消则返回 None
        """
        if filetypes is None:
            filetypes = [("Excel Files", "*.xlsx"), ("All Files", "*.*")]
        
        root = tk.Tk()
        root.withdraw()
        
        file_path = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes,
            initialdir=initialdir
        )
        
        root.destroy()
        
        return file_path if file_path else None
    
    @staticmethod
    def select_folder(title: str = "选择文件夹") -> Optional[str]:
        """
        选择文件夹
        
        Args:
            title: 对话框标题
        
        Returns:
            选中的文件夹路径，如果取消则返回 None
        """
        root = tk.Tk()
        root.withdraw()
        
        folder_path = filedialog.askdirectory(title=title)
        
        root.destroy()
        
        return folder_path if folder_path else None
    
    @staticmethod
    def show_result(
        success: bool,
        message: str,
        details: dict = None
    ) -> None:
        """
        显示结果总结
        
        Args:
            success: 是否成功
            message: 主要信息
            details: 详细信息字典
        """
        if details:
            detail_text = "\n".join([f"  • {k}: {v}" for k, v in details.items()])
            full_message = f"{message}\n\n详细信息：\n{detail_text}"
        else:
            full_message = message
        
        if success:
            UIManager.show_info("成功", full_message)
        else:
            UIManager.show_error("失败", full_message)
