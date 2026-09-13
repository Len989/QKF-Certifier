protected Stamp foldStampImpl(Stamp stamp1, Stamp stamp2) {
                            if (stamp1.isEmpty()) {
                                return stamp1;
                            }
                            if (stamp2.isEmpty()) {
                                return stamp2;
                            }
                            IntegerStamp a = (IntegerStamp) stamp1;
                            IntegerStamp b = (IntegerStamp) stamp2;
                            assert a.getBits() == b.getBits() : "Bits must match " + Assertions.errorMessageContext("a", a, "b", b);

                            return stampForMask(a.getBits(), a.mustBeSet() | b.mustBeSet(), a.mayBeSet() | b.mayBeSet());
                        }
