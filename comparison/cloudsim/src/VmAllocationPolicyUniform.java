import org.cloudbus.cloudsim.VmAllocationPolicy;
import org.cloudbus.cloudsim.core.GuestEntity;
import org.cloudbus.cloudsim.core.HostEntity;

import java.util.List;

public class VmAllocationPolicyUniform extends VmAllocationPolicy {

    private final int maxVmsPerHost;

    public VmAllocationPolicyUniform(List<? extends HostEntity> hostList, int maxVmsPerHost) {
        super(hostList);
        this.maxVmsPerHost = Math.max(1, maxVmsPerHost);
    }

    @Override
    public HostEntity findHostForGuest(GuestEntity guest) {
        for (HostEntity host : getHostList()) {
            if (host.getGuestList().size() < maxVmsPerHost && host.isSuitableForGuest(guest)) {
                return host;
            }
        }
        return null;
    }
}

