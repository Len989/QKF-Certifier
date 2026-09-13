protected Stamp foldStampImpl(Stamp stamp1, Stamp stamp2) {
                            if (stamp1.isEmpty()) {
                                return stamp1;
                            }
                            if (stamp2.isEmpty()) {
                                return stamp2;
                            }
                            IntegerStamp a = (IntegerStamp) stamp1;
                            IntegerStamp b = (IntegerStamp) stamp2;

                            int bits = a.getBits();
                            assert bits == b.getBits() : String.format("stamp1.bits=%d, stamp2.bits=%d", bits, b.getBits());

                            if (a.lowerBound == a.upperBound && b.lowerBound == b.upperBound) {
                                long value = CodeUtil.convert(a.lowerBound() + b.lowerBound(), a.getBits(), false);
                                return createConstant(a.getBits(), value);
                            }

                            if (a.isUnrestricted()) {
                                return a;
                            } else if (b.isUnrestricted()) {
                                return b;
                            }
                            long defaultMask = CodeUtil.mask(bits);
                            long variableBits = (a.mustBeSet() ^ a.mayBeSet()) | (b.mustBeSet() ^ b.mayBeSet());
                            long variableBitsWithCarry = variableBits | (carryBits(a.mustBeSet(), b.mustBeSet()) ^ carryBits(a.mayBeSet(), b.mayBeSet()));
                            long newMustBeSet = (a.mustBeSet() + b.mustBeSet()) & ~variableBitsWithCarry;
                            long newMayBeSet = (a.mustBeSet() + b.mustBeSet()) | variableBitsWithCarry;

                            newMustBeSet &= defaultMask;
                            newMayBeSet &= defaultMask;

                            long newLowerBound;
                            long newUpperBound;
                            boolean lowerOverflowsPositively = addOverflowsPositively(a.lowerBound(), b.lowerBound(), bits);
                            boolean upperOverflowsPositively = addOverflowsPositively(a.upperBound(), b.upperBound(), bits);
                            boolean lowerOverflowsNegatively = addOverflowsNegatively(a.lowerBound(), b.lowerBound(), bits);
                            boolean upperOverflowsNegatively = addOverflowsNegatively(a.upperBound(), b.upperBound(), bits);
                            if ((lowerOverflowsNegatively && !upperOverflowsNegatively) || (!lowerOverflowsPositively && upperOverflowsPositively)) {
                                newLowerBound = CodeUtil.minValue(bits);
                                newUpperBound = CodeUtil.maxValue(bits);
                            } else {
                                newLowerBound = CodeUtil.signExtend((a.lowerBound() + b.lowerBound()) & defaultMask, bits);
                                newUpperBound = CodeUtil.signExtend((a.upperBound() + b.upperBound()) & defaultMask, bits);
                            }
                            IntegerStamp limit = create(bits, newLowerBound, newUpperBound);
                            newMayBeSet &= limit.mayBeSet();
                            newUpperBound = CodeUtil.signExtend(newUpperBound & newMayBeSet, bits);
                            newMustBeSet |= limit.mustBeSet();
                            newLowerBound |= newMustBeSet;
                            return IntegerStamp.create(bits, newLowerBound, newUpperBound, newMustBeSet, newMayBeSet);
                        }
