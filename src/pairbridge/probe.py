"""Execute a bounded subset of actual Xtensa instructions from S305.

This verifies only the parameter-validation block, with the default register
values established by the preceding instructions. It is not a full firmware,
radio, bootloader or pairing emulator.
"""

ENTRY = 0x639D6
EDIT = 0x639DF
ACCEPT = 0x639FA
FALLBACK = 0x63A2C
ORIGINAL = bytes.fromhex('520a03 920a04 871502 664540 608074 87993a 920a05 708074 879931')
PATCHED = bytes.fromhex('520a04 608074 879543 920a05 909064 708074 879937 860000 f02000')
PREFIX = bytes.fromhex('b20a01 408074 579b4c')


def require(condition, message):
    # Validation must also run when Python is started with -O.
    if not condition:
        raise ValueError(message)


def signed(number, bits):
    return number - (1 << bits) if number & (1 << (bits - 1)) else number


def execute(code, pdu, expected_command=10, expected_byte3=1,
            expected_byte4=0, expected_byte5=0):
    if len(pdu) != 6 or pdu[0] >> 1 != 123:
        raise ValueError('Probe requires a six-byte opcode123 PDU')
    registers = [0] * 16
    registers[4] = expected_byte3
    registers[5] = expected_command
    registers[6] = expected_byte4
    registers[7] = expected_byte5
    registers[10] = 0x1000
    pc = ENTRY
    visited = []
    for _ in range(30):
        if pc in (ACCEPT, FALLBACK):
            return {'decision': 'reply_path' if pc == ACCEPT else 'fallback_path',
                    'destination': hex(pc), 'visited': visited}
        index = pc - ENTRY
        if not 0 <= index <= len(code) - 3:
            raise ValueError(f'Probe left validation block at {pc:x}')
        word = int.from_bytes(code[index:index + 3], 'little')
        next_pc = pc + 3
        op = word & 15
        visited.append(hex(pc))
        if word == 0x0020F0:  # NOP
            pass
        elif word & 63 == 6:  # J, signed 18-bit byte displacement
            next_pc = pc + 4 + signed(word >> 6, 18)
        elif op == 2 and (word >> 12) & 15 == 0:  # L8UI
            dest, base, offset = (word >> 4) & 15, (word >> 8) & 15, word >> 16
            address = registers[base] + offset - 0x1000
            if not 0 <= address < len(pdu):
                raise ValueError('Load left PDU buffer')
            registers[dest] = pdu[address]
        elif op == 0 and (word >> 16) & 15 == 4:  # EXTUI, shifts 0..15 here
            src, dest = (word >> 4) & 15, (word >> 12) & 15
            shift, size = (word >> 8) & 15, ((word >> 20) & 15) + 1
            registers[dest] = (registers[src] >> shift) & ((1 << size) - 1)
        elif op == 7 and (word >> 12) & 15 in (1, 9):  # BEQ / BNE
            left, right = (word >> 8) & 15, (word >> 4) & 15
            same = registers[left] == registers[right]
            condition = same if (word >> 12) & 15 == 1 else not same
            if condition:
                next_pc = pc + 4 + signed(word >> 16, 8)
        elif op == 6 and (word >> 4) & 15 == 6:  # BNEI in this block
            source, immediate = (word >> 8) & 15, (word >> 12) & 15
            if immediate != 4:
                raise ValueError('Unsupported immediate table entry')
            if registers[source] != immediate:
                next_pc = pc + 4 + signed(word >> 16, 8)
        else:
            raise ValueError(f'Unsupported instruction {word:06x} at {pc:x}')
        pc = next_pc
    raise ValueError('Probe instruction budget exhausted')


def verify(stock, old_trace, new_trace):
    if stock[ENTRY:EDIT] != PREFIX or stock[EDIT:ACCEPT] != ORIGINAL:
        raise ValueError('Stock code does not match the decoded validation block')
    rows = []
    for device, trace in [('iPhone11', old_trace), ('iPhone17', new_trace)]:
        requests = [bytes.fromhex(m['pdu_hex']) for m in trace['messages']
                    if m['opcode'] == 123 and m['direction'] == 'host_to_earbuds']
        if len(requests) != 2:
            raise ValueError('Expected two observed requests per phone')
        for pdu in requests:
            original = execute(PREFIX + ORIGINAL, pdu)
            patched = execute(PREFIX + PATCHED, pdu)
            require(original['decision'] == ('reply_path' if device == 'iPhone11' else 'fallback_path'),
                    'Recorded request no longer reproduces the original branch')
            require(patched['decision'] == 'reply_path', 'Recorded request fails the patched branch')
            rows.append({'device': device, 'pdu_hex': pdu.hex(),
                         'original': original, 'patched': patched})
    checks = 0
    for command in range(256):
        pdu = bytes([0xf6, command, 0xf6, 0x76, 0, 0x80])
        decision = execute(PREFIX + PATCHED, pdu)['decision']
        require(decision == ('reply_path' if command == 10 else 'fallback_path'), 'Command gate changed')
        checks += 1
    for byte4 in range(256):
        for high in (0, 128):
            pdu = bytes([0xf6, 10, 0xf6, 0x76, byte4, high])
            require(execute(PREFIX + PATCHED, pdu)['decision'] == ('reply_path' if byte4 == 0 else 'fallback_path'),
                    'Byte4 gate changed')
            checks += 1
    for byte5 in range(256):
        pdu = bytes([0xf6, 10, 0xf6, 0x76, 0, byte5])
        require(execute(PREFIX + PATCHED, pdu)['decision'] == ('reply_path' if byte5 in (0, 128) else 'fallback_path'),
                'Byte5 low-bit gate changed')
        checks += 1
    for byte3 in range(256):
        pdu = bytes([0xf6, 10, 0x1f, byte3, 0, 0])
        require(execute(PREFIX + ORIGINAL, pdu)['decision'] == ('reply_path' if byte3 in (1, 4) else 'fallback_path'),
                'Original byte3 gate changed')
        require(execute(PREFIX + PATCHED, pdu)['decision'] == 'reply_path', 'Patched byte3 gate changed')
        checks += 2
    for tid in (0, 1):
        require(execute(PREFIX + PATCHED, bytes([0xf6 | tid, 10, 0xf6, 0x76, 0, 128]))['decision'] == 'reply_path',
                'Transaction-ID handling changed')
        checks += 1
    return {'observed_requests': rows, 'additional_checks_passed': checks,
            'original_17_request_reproduces_fallback': True,
            'patched_17_request_reaches_existing_reply_path': True,
            'old_11_request_still_reaches_reply_path': True,
            'scope': 'Actual decoded machine instructions in the parameter block; default configuration registers only',
            'full_firmware_emulated': False, 'hardware_tested': False}
