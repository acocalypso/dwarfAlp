// Focused offline Ghidra trace. Output contains decompiled vendor code and must remain local.
// @category Dwarflab
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class ExportScheduleHandlers extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) throw new IllegalArgumentException("Output path required");
        Set<Function> selected = new LinkedHashSet<>();
        for (int i = 1; i < args.length; i++) {
            ghidra.program.model.address.Address address = toAddr(args[i]);
            Function f = getFunctionAt(address);
            if (f == null) {
                disassemble(address);
                f = createFunction(address, null);
            }
            if (f != null) selected.add(f);
        }
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            out.println("Program: " + currentProgram.getName());
            out.println("Executable SHA256: " + currentProgram.getExecutableSHA256());
            DataIterator data = currentProgram.getListing().getDefinedData(true);
            while (data.hasNext() && !monitor.isCancelled()) {
                Data item = data.next();
                if (!item.hasStringValue()) continue;
                String value = String.valueOf(item.getValue());
                if (!(value.equals("getAllShootingSchedule") || value.equals("syncShootingSchedule")
                    || value.equals("wsResSyncShootingSchedule") || value.equals("wsResGetShootingScheduleById")
                    || value.equals("getShootingScheduleById") || value.equals("processShootingScheduleInfo"))) continue;
                out.println("STRING " + item.getAddress() + " " + value);
                ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(item.getAddress());
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Function f = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                    out.println("  REF " + ref.getFromAddress() + " " + (f == null ? "unknown" : f.getEntryPoint()));
                    if (f != null) selected.add(f);
                }
            }
            Set<Function> callers = new LinkedHashSet<>();
            for (Function f : selected) {
                for (Function caller : f.getCallingFunctions(monitor)) callers.add(caller);
            }
            selected.addAll(callers);
            DecompInterface decompiler = new DecompInterface();
            try {
                decompiler.openProgram(currentProgram);
                for (Function f : selected) {
                    out.println("\nFUNCTION " + f.getEntryPoint() + " " + f.getName());
                    DecompileResults result = decompiler.decompileFunction(f, 45, monitor);
                    if (result.decompileCompleted()) out.println(result.getDecompiledFunction().getC());
                    else out.println("DECOMPILE FAILED: " + result.getErrorMessage());
                    out.flush();
                }
            } finally { decompiler.dispose(); }
            out.println("FUNCTION COUNT " + selected.size());
        }
    }
}
